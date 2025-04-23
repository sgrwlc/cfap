# tests/integration/api/test_seller_campaign_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for Seller Campaign Management endpoints (/api/seller/campaigns),
aligned with refactored services and routes.
"""
import json
import pytest
import logging

# Import Models for DB checks and setup helpers
from app.database.models import (
    CampaignModel, UserModel, DidModel, ClientModel,
    CampaignDidModel, CampaignClientSettingsModel
)
# Import Services for setup (using session fixture for transaction control)
from app.services.campaign_service import CampaignService
from app.services.user_service import UserService
from app.services.did_service import DidService
from app.services.client_service import ClientService # Only needed if creating clients in tests

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_client (seller), logged_in_admin_client

# Helper to get seller ID
def get_seller_id(session):
    user = session.query(UserModel).filter_by(username="pytest_seller").one()
    return user.id

# Helper to create campaign via service (relies on session fixture rollback)
def create_campaign_via_service(session, user_id, name, **kwargs):
    camp = CampaignService.create_campaign(user_id=user_id, name=name, **kwargs)
    session.flush()
    log.debug(f"Setup: Created Campaign '{name}' (ID: {camp.id}) for user {user_id} via service.")
    return camp

# Helper to create DID via service (relies on session fixture rollback)
def create_did_via_service(session, user_id, number, **kwargs):
    did = DidService.add_did(user_id=user_id, number=number, **kwargs)
    session.flush()
    log.debug(f"Setup: Created DID '{number}' (ID: {did.id}) for user {user_id} via service.")
    return did

# Helper to link client via service (relies on session fixture rollback)
def link_client_via_service(session, camp_id, user_id, client_id, settings):
    setting = CampaignService.add_client_to_campaign(camp_id, user_id, client_id, settings)
    session.flush()
    log.debug(f"Setup: Linked Client {client_id} to Campaign {camp_id} (Setting ID: {setting.id}).")
    return setting

# Helper to set DIDs via service (relies on session fixture rollback)
def set_dids_via_service(session, camp_id, user_id, did_ids):
    success = CampaignService.set_campaign_dids(camp_id, user_id, did_ids)
    session.flush()
    log.debug(f"Setup: Set DIDs {did_ids} for Campaign {camp_id}.")
    return success

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
    assert response.status_code == 201, f"API Setup Failed: Create client '{identifier}'. Status: {response.status_code}, Response: {response.data.decode()}"
    return json.loads(response.data)

# --- Test GET /api/seller/campaigns ---

def test_seller_get_own_campaigns_list(logged_in_client, session):
    """
    GIVEN seller client logged in and seller owns campaigns (created via service)
    WHEN GET /api/seller/campaigns requested
    THEN check status 200 and only own campaigns are returned.
    """
    log.debug("Running test_seller_get_own_campaigns_list")
    # Arrange: Create campaigns via service within session transaction
    seller_id = get_seller_id(session)
    camp1 = create_campaign_via_service(session, seller_id, "My First Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    camp2 = create_campaign_via_service(session, seller_id, "My Second Camp P5", routing_strategy="round_robin", dial_timeout_seconds=25, status='inactive')
    # Create campaign for another user (should not appear)
    other_user = UserService.create_user("otherseller_camp_p5", "other_camp_p5@s.com", "Pass123")
    session.flush()
    create_campaign_via_service(session, other_user.id, "Other Seller Camp P5", routing_strategy="priority", dial_timeout_seconds=30)

    # Act: Call API
    response = logged_in_client.get('/api/seller/campaigns?page=1&per_page=10')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 2 # Only the 2 for pytest_seller
    assert len(data['items']) == 2
    names_returned = {item['name'] for item in data['items']}
    assert camp1.name in names_returned
    assert camp2.name in names_returned
    assert "Other Seller Camp P5" not in names_returned
    assert 'clientSettings' not in data['items'][0] # List view excludes details
    log.debug("Finished test_seller_get_own_campaigns_list")


def test_seller_get_campaigns_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/seller/campaigns requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/seller/campaigns')
    assert response.status_code == 401


# --- Test POST /api/seller/campaigns ---

def test_seller_create_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/campaigns with valid data
    THEN check status 201 Created and campaign added to DB for that seller.
    """
    log.debug("Running test_seller_create_campaign_success")
    seller_id = get_seller_id(session)
    campaign_payload = {
        "name": "Seller Created Camp P5", "routingStrategy": "weighted",
        "dialTimeoutSeconds": 28, "description": "Created via API P5", "status": "active"
    }

    # Act: Call API (handles commit)
    response = logged_in_client.post('/api/seller/campaigns', json=campaign_payload)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['name'] == campaign_payload['name']
    assert data['routingStrategy'] == campaign_payload['routingStrategy']
    assert data['dialTimeoutSeconds'] == campaign_payload['dialTimeoutSeconds']
    assert 'id' in data
    campaign_id = data['id']

    # Assert Database State
    campaign_db = session.get(CampaignModel, campaign_id) # Use session.get
    assert campaign_db is not None
    assert campaign_db.user_id == seller_id
    assert campaign_db.name == campaign_payload['name']
    log.debug("Finished test_seller_create_campaign_success")


def test_seller_create_campaign_duplicate_name_fail(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign with a specific name
    WHEN POST /api/seller/campaigns with the same name
    THEN check status 409 Conflict.
    """
    # Arrange: Create initial campaign via service
    seller_id = get_seller_id(session)
    existing_name = "Duplicate Camp Name P5"
    create_campaign_via_service(session, seller_id, existing_name, routing_strategy="priority", dial_timeout_seconds=30)

    campaign_payload = { "name": existing_name, "routingStrategy": "round_robin", "dialTimeoutSeconds": 20 }

    # Act: Call API
    response = logged_in_client.post('/api/seller/campaigns', json=campaign_payload)

    # Assert: Route catches ConflictError
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Campaign name '{existing_name}' already exists" in data.get('message', '')


def test_seller_create_campaign_missing_name(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/campaigns without 'name'
    THEN check status 400 Bad Request (schema validation).
    """
    campaign_payload = {"routingStrategy": "priority", "dialTimeoutSeconds": 25}
    response = logged_in_client.post('/api/seller/campaigns', json=campaign_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data and 'name' in data['errors']


# --- Test GET /api/seller/campaigns/{campaign_id} ---

def test_seller_get_own_campaign_success(logged_in_client, session):
    """
    GIVEN seller logged in, owns campaign with links (created via service)
    WHEN GET /api/seller/campaigns/{campaign_id} requested
    THEN check status 200 OK and full campaign details (incl links) returned.
    """
    log.debug("Running test_seller_get_own_campaign_success")
    # Arrange: Create campaign, DID, Client link via service
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Get Detailed Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    did = create_did_via_service(session, seller_id, "+15553334444_p5")
    client1 = session.get(ClientModel, 1) # Assume client 1 exists from sample data
    assert client1 is not None, "Client ID 1 not found in sample data"

    # Call services to stage links (NO explicit commit here)
    set_dids_via_service(session, campaign.id, seller_id, [did.id])
    setting1 = link_client_via_service(session, campaign.id, seller_id, client1.id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })
    target_id = campaign.id

    # Act: Call API (reads committed state if services didn't commit, or reads from transaction if they did flush)
    response = logged_in_client.get(f'/api/seller/campaigns/{target_id}')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['name'] == "Get Detailed Camp P5"
    assert len(data.get('dids', [])) == 1
    assert data['dids'][0]['id'] == did.id
    assert len(data.get('clientSettings', [])) == 1
    assert data['clientSettings'][0]['id'] == setting1.id
    assert data['clientSettings'][0]['client']['id'] == client1.id
    log.debug("Finished test_seller_get_own_campaign_success")


def test_seller_get_other_campaign_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/campaigns/{campaign_id} for another user's campaign
    THEN check status 404 Not Found.
    """
    # Arrange: Create campaign for another user via service
    other_user = UserService.create_user("otherseller_camp2_p5", "other_camp2_p5@s.com", "Pass123")
    session.flush()
    other_campaign = create_campaign_via_service(session, other_user.id, "Other Seller Camp 2 P5", routing_strategy="priority", dial_timeout_seconds=30)
    target_id = other_campaign.id

    # Act
    response = logged_in_client.get(f'/api/seller/campaigns/{target_id}')

    # Assert: Route/Service checks ownership
    assert response.status_code == 404


def test_seller_get_nonexistent_campaign_fail(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/campaigns/{campaign_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_client.get('/api/seller/campaigns/999999')
    assert response.status_code == 404


# --- Test PUT /api/seller/campaigns/{campaign_id} ---

def test_seller_update_own_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign
    WHEN PUT /api/seller/campaigns/{campaign_id} with valid update data
    THEN check status 200 OK and campaign is updated.
    """
    # Arrange: Create campaign via service
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Update Camp Test P5", routing_strategy="priority", dial_timeout_seconds=30, status="active")
    target_id = campaign.id
    update_payload = {
        "name": "Update Camp Test P5 (UPDATED)", "routingStrategy": "round_robin",
        "status": "paused", "dialTimeoutSeconds": 45
    }

    # Act: Call API (handles commit)
    response = logged_in_client.put(f'/api/seller/campaigns/{target_id}', json=update_payload)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['name'] == update_payload['name']
    assert data['status'] == update_payload['status']

    # Assert Database
    campaign_db = session.get(CampaignModel, target_id) # Re-fetch
    assert campaign_db.name == update_payload['name']
    assert campaign_db.routing_strategy == update_payload['routingStrategy']
    assert campaign_db.status == update_payload['status']
    assert campaign_db.dial_timeout_seconds == update_payload['dialTimeoutSeconds']


def test_seller_update_other_campaign_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN PUT /api/seller/campaigns/{campaign_id} for another user's campaign
    THEN check status 403 Forbidden or 404 Not Found.
    """
    # Arrange
    other_user = UserService.create_user("otherseller_camp3_p5", "other_camp3_p5@s.com", "Pass123")
    session.flush()
    other_campaign = create_campaign_via_service(session, other_user.id, "Other Seller Camp 3 P5", routing_strategy="priority", dial_timeout_seconds=30)
    target_id = other_campaign.id
    update_payload = {"name": "Attempted Update P5"}

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{target_id}', json=update_payload)

    # Assert: Route catches ResourceNotFound or AuthorizationError
    assert response.status_code in [403, 404]


def test_seller_update_campaign_duplicate_name_fail(logged_in_client, session):
    """
    GIVEN seller client logged in and owns two campaigns
    WHEN PUT tries to rename one to match the other
    THEN check status 409 Conflict.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign1 = create_campaign_via_service(session, seller_id, "Unique Name Camp 1 P5", routing_strategy="priority", dial_timeout_seconds=30)
    campaign2 = create_campaign_via_service(session, seller_id, "Unique Name Camp 2 P5", routing_strategy="priority", dial_timeout_seconds=30)
    update_payload = {"name": campaign1.name} # Try renaming campaign2

    # Act: Call API
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign2.id}', json=update_payload)

    # Assert: Route catches ConflictError
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Campaign name '{campaign1.name}' already exists" in data.get('message', '')


# --- Test DELETE /api/seller/campaigns/{campaign_id} ---

def test_seller_delete_own_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign (with links)
    WHEN DELETE /api/seller/campaigns/{campaign_id} requested
    THEN check status 204 No Content and campaign + links removed.
    """
    log.debug("Running test_seller_delete_own_campaign_success")
    # Arrange
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Delete Camp Test P5", routing_strategy="priority", dial_timeout_seconds=30)
    did = create_did_via_service(session, seller_id, "+15554445555_p5")
    client1 = session.get(ClientModel, 1)
    assert client1 is not None
    # Stage links via service (no commit)
    set_dids_via_service(session, campaign.id, seller_id, [did.id])
    setting1 = link_client_via_service(session, campaign.id, seller_id, client1.id, {
        "max_concurrency": 2, "forwarding_priority": 0, "weight": 100
    })
    target_id = campaign.id
    setting1_id = setting1.id

    # Verify links exist in session before API call
    assert session.get(CampaignModel, target_id) is not None
    assert session.query(CampaignDidModel).filter_by(campaign_id=target_id).count() > 0
    assert session.get(CampaignClientSettingsModel, setting1_id) is not None

    # Act: Call API (handles commit)
    response = logged_in_client.delete(f'/api/seller/campaigns/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database (Check cascade delete worked)
    assert session.get(CampaignModel, target_id) is None
    assert session.query(CampaignDidModel).filter_by(campaign_id=target_id).count() == 0
    assert session.get(CampaignClientSettingsModel, setting1_id) is None
    log.debug("Finished test_seller_delete_own_campaign_success")


def test_seller_delete_other_campaign_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN DELETE /api/seller/campaigns/{campaign_id} for another user's campaign
    THEN check status 403 Forbidden or 404 Not Found.
    """
    # Arrange
    other_user = UserService.create_user("otherseller_camp4_p5", "other_camp4_p5@s.com", "Pass123")
    session.flush()
    other_campaign = create_campaign_via_service(session, other_user.id, "Other Seller Camp 4 P5", routing_strategy="priority", dial_timeout_seconds=30)
    target_id = other_campaign.id

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{target_id}')

    # Assert: Route catches ResourceNotFound or AuthorizationError
    assert response.status_code in [403, 404]


# --- Test PUT /api/seller/campaigns/{campaign_id}/dids ---

def test_seller_set_campaign_dids_success(logged_in_client, session):
    """
    GIVEN seller logged in, owns campaign and DIDs
    WHEN PUT /api/seller/campaigns/{id}/dids with valid owned DID IDs
    THEN check status 200 OK and links updated in DB.
    """
    # Arrange: Setup via service (no commit)
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Set DIDs Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    did1 = create_did_via_service(session, seller_id, "+15550101010_p5")
    did2 = create_did_via_service(session, seller_id, "+15550101011_p5")
    did3 = create_did_via_service(session, seller_id, "+15550101012_p5")
    set_dids_via_service(session, campaign.id, seller_id, [did1.id]) # Initial link
    campaign_id = campaign.id

    # Act: Call API (handles commit)
    payload = {"didIds": [did2.id, did3.id]} # Replace did1 with did2, did3
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json=payload)

    # Assert Response
    assert response.status_code == 200

    # Assert Database state
    links = session.query(CampaignDidModel).filter_by(campaign_id=campaign_id).all()
    linked_did_ids = {link.did_id for link in links}
    assert len(links) == 2
    assert did1.id not in linked_did_ids
    assert did2.id in linked_did_ids
    assert did3.id in linked_did_ids


def test_seller_set_campaign_dids_clear_success(logged_in_client, session):
    """
    GIVEN seller logged in, owns campaign with linked DIDs
    WHEN PUT /api/seller/campaigns/{id}/dids with empty list
    THEN check status 200 OK and all links are removed.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Clear DIDs Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    did1 = create_did_via_service(session, seller_id, "+15550202020_p5")
    set_dids_via_service(session, campaign.id, seller_id, [did1.id])
    campaign_id = campaign.id
    assert session.query(CampaignDidModel).filter_by(campaign_id=campaign_id).count() == 1 # Verify initial

    # Act: Call API with empty list (handles commit)
    payload = {"didIds": []}
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json=payload)

    # Assert Response
    assert response.status_code == 200

    # Assert Database state
    assert session.query(CampaignDidModel).filter_by(campaign_id=campaign_id).count() == 0


def test_seller_set_campaign_dids_fail_did_not_owned(logged_in_client, session):
    """
    GIVEN seller logged in, owns campaign
    WHEN PUT /api/seller/campaigns/{id}/dids includes DID ID not owned by seller
    THEN check status 403 Forbidden.
    """
     # Arrange
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Not Owned DID Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    other_user = UserService.create_user("otherseller_didlink_p5", "other_link_p5@s.com", "Pass123")
    session.flush()
    other_did = create_did_via_service(session, other_user.id, "+15550303030_p5")
    campaign_id = campaign.id

    # Act: Call API trying to link other user's DID
    payload = {"didIds": [other_did.id]}
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json=payload)

    # Assert: Route catches AuthorizationError
    assert response.status_code == 403 # Service raises AuthorizationError specifically for DID ownership
    assert "not owned by the user" in json.loads(response.data).get('message', '')


def test_seller_set_campaign_dids_fail_campaign_not_owned(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN PUT /api/seller/campaigns/{id}/dids for campaign owned by another user
    THEN check status 404 Not Found.
    """
    # Arrange
    seller_id = get_seller_id(session)
    my_did = create_did_via_service(session, seller_id, "+15550404040_p5")
    other_user = UserService.create_user("otherseller_didlink2_p5", "other_link2_p5@s.com", "Pass123")
    session.flush()
    other_campaign = create_campaign_via_service(session, other_user.id, "Other User Set DID Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    other_campaign_id = other_campaign.id
    payload = {"didIds": [my_did.id]}

    # Act: Call API for other user's campaign
    response = logged_in_client.put(f'/api/seller/campaigns/{other_campaign_id}/dids', json=payload)

    # Assert: Route catches ResourceNotFound or AuthorizationError -> maps to 404 for campaign access
    assert response.status_code == 404


# --- Test GET /api/seller/campaigns/available_clients ---

# --- Replace the existing test_seller_get_available_clients in tests/integration/api/test_seller_campaign_api.py ---

def test_seller_get_available_clients(logged_in_client, session): # Remove logged_in_admin_client fixture dependency
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/campaigns/available_clients requested
    THEN check status 200 OK and only active clients are listed.
    """
    log.debug("Running test_seller_get_available_clients")
    # Arrange: Ensure an inactive client exists using the service layer directly
    # Get admin user ID from sample data (assuming admin user exists)
    admin_user = session.query(UserModel).filter_by(username="platform_admin").one_or_none()
    if not admin_user:
         # If admin user from sample data wasn't found, create one for this test scope
         admin_user = UserService.create_user(
             username="temp_admin_for_client",
             email="temp_admin@test.local",
             password="TempAdminPass1!",
             role="admin"
         )
         session.flush()
         log.warning("Sample admin 'platform_admin' not found, created temporary admin for client setup.")
    admin_id = admin_user.id

    identifier_inactive = "inactive_test_p5_setup"
    try:
        # Create client using service (won't commit by itself)
        # Need to ensure ClientService is imported at the top
        inactive_client = ClientService.create_client_with_pjsip(
            creator_user_id=admin_id,
            client_data={"client_identifier": identifier_inactive, "name": "Inactive P5 Setup", "status": "inactive"},
            pjsip_data={
                "endpoint": {"id": identifier_inactive, "context": "ctx-inactive", "aors": identifier_inactive},
                "aor": {"id": identifier_inactive, "contact": "sip:inactive_p5_setup"}
            }
        )
        session.flush() # Flush to ensure it exists in transaction for the test's API call
        log.debug(f"Setup: Created inactive client ID {inactive_client.id} via service")
    except Exception as e:
        log.error(f"Setup Error in test_seller_get_available_clients: {e}", exc_info=True)
        # Allow potential ConflictError if running tests multiple times without clean DB?
        # Or better, ensure identifier is unique per run if possible.
        if "already exists" in str(e):
             log.warning(f"Client '{identifier_inactive}' likely already exists from previous failed run. Continuing test.")
        else:
             pytest.fail(f"Failed to create inactive client during test setup: {e}")

    # Act: Seller requests available clients using the logged_in_client fixture
    response = logged_in_client.get('/api/seller/campaigns/available_clients')

    # Assert
    assert response.status_code == 200
    try:
        data = json.loads(response.data)
    except json.JSONDecodeError:
        pytest.fail(f"Failed to decode JSON response: {response.data}")

    assert isinstance(data, list), f"Expected response data to be a list, got {type(data)}"
    identifiers = {item.get('clientIdentifier') for item in data if item.get('clientIdentifier')}

    # Check that known active clients from sample data are present
    assert 'client_alpha_sales' in identifiers, "Expected active client 'client_alpha_sales' not found"
    assert 'client_beta_support' in identifiers, "Expected active client 'client_beta_support' not found"
    assert 'client_gamma_intake' in identifiers, "Expected active client 'client_gamma_intake' not found"
    # Check that the inactive client created in setup is NOT present
    assert identifier_inactive not in identifiers, f"Inactive client '{identifier_inactive}' was unexpectedly found"
    # Check schema includes only expected fields
    if data: # Ensure list is not empty before checking first item
        assert 'id' in data[0]
        assert 'name' in data[0]
        assert 'department' in data[0]
        assert 'clientIdentifier' in data[0]
        assert 'status' not in data[0], "Status field should not be present for active clients list"
        assert 'pjsipEndpoint' not in data[0], "PJSIP details should be excluded by the simple schema"
    log.debug("Finished test_seller_get_available_clients")

# --- Test POST /api/seller/campaigns/{campaign_id}/clients ---

def test_seller_add_client_link_success(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign, client exists
    WHEN POST /api/seller/campaigns/{id}/clients with valid settings
    THEN check status 201 Created and link added.
    """
    log.debug("Running test_seller_add_client_link_success")
    # Arrange
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Link Client Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    client_id = 2 # Beta (from sample data)
    campaign_id = campaign.id
    settings_payload = {
        "clientId": client_id, "maxConcurrency": 7, "totalCallsAllowed": 500,
        "forwardingPriority": 1, "weight": 150, "status": "active"
    }

    # Act: Call API (handles commit)
    response = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings_payload)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['client']['id'] == client_id
    assert data['maxConcurrency'] == settings_payload['maxConcurrency']
    assert 'id' in data
    setting_id = data['id']

    # Assert Database
    setting_db = session.get(CampaignClientSettingsModel, setting_id)
    assert setting_db is not None
    assert setting_db.campaign_id == campaign_id
    assert setting_db.client_id == client_id
    log.debug("Finished test_seller_add_client_link_success")


def test_seller_add_client_link_duplicate_fail(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign, client already linked
    WHEN POST /api/seller/campaigns/{id}/clients for the same client
    THEN check status 409 Conflict.
    """
    # Arrange: Create campaign and link client via service
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Duplicate Link Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    client_id = 1 # Alpha
    link_client_via_service(session, campaign.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })
    campaign_id = campaign.id
    # Payload to add the same client again
    settings_payload = {"clientId": client_id, "maxConcurrency": 1, "forwardingPriority": 1, "weight": 1}

    # Act: Call API
    response = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings_payload)

    # Assert: Route catches ConflictError
    assert response.status_code == 409
    assert f"Client {client_id} is already linked" in json.loads(response.data).get('message', '')


def test_seller_add_client_link_missing_settings(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign, client exists
    WHEN POST /api/seller/campaigns/{id}/clients missing required settings
    THEN check status 400 Bad Request (schema validation).
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Missing Settings Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    client_id = 1 # Alpha
    campaign_id = campaign.id
    # Missing maxConcurrency, forwardingPriority, weight
    settings_payload = {"clientId": client_id}

    # Act
    response = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings_payload)

    # Assert
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'errors' in data
    assert 'maxConcurrency' in data['errors']
    assert 'forwardingPriority' in data['errors']
    assert 'weight' in data['errors']


# --- Test PUT /api/seller/campaigns/{campaign_id}/clients/{setting_id} ---

def test_seller_update_client_setting_success(logged_in_client, session):
    """
    GIVEN seller logged in, owns campaign and setting link
    WHEN PUT /api/seller/campaigns/{cid}/clients/{sid} with valid updates
    THEN check status 200 OK and settings updated.
    """
    log.debug("Running test_seller_update_client_setting_success")
    # Arrange
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Update Setting Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    client_id = 1 # Alpha
    setting = link_client_via_service(session, campaign.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100, "status": "active"
    })
    campaign_id = campaign.id
    setting_id = setting.id
    update_payload = {"maxConcurrency": 8, "status": "inactive", "forwardingPriority": 10}

    # Act: Call API (handles commit)
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/clients/{setting_id}', json=update_payload)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == setting_id
    assert data['maxConcurrency'] == 8
    assert data['status'] == "inactive"
    assert data['forwardingPriority'] == 10
    assert data['weight'] == 100 # Unchanged

    # Assert Database
    setting_db = session.get(CampaignClientSettingsModel, setting_id) # Re-fetch
    assert setting_db.max_concurrency == 8
    assert setting_db.status == "inactive"
    assert setting_db.forwarding_priority == 10
    log.debug("Finished test_seller_update_client_setting_success")


def test_seller_update_client_setting_fail_not_found(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign
    WHEN PUT /api/seller/campaigns/{cid}/clients/{sid} for non-existent setting ID
    THEN check status 404 Not Found.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Update Missing Setting Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    campaign_id = campaign.id
    update_payload = {"status": "inactive"}

    # Act: Call API for non-existent setting
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/clients/999999', json=update_payload)

    # Assert: Route catches ResourceNotFound
    assert response.status_code == 404


def test_seller_update_client_setting_fail_wrong_campaign(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaigns A & B, setting exists for camp A
    WHEN PUT /api/seller/campaigns/{camp_B_id}/clients/{setting_A_id}
    THEN check status 404 Not Found (route pre-check/service auth check).
    """
    # Arrange
    seller_id = get_seller_id(session)
    camp_a = create_campaign_via_service(session, seller_id, "Update Wrong Camp A P5", routing_strategy="priority", dial_timeout_seconds=30)
    camp_b = create_campaign_via_service(session, seller_id, "Update Wrong Camp B P5", routing_strategy="priority", dial_timeout_seconds=30)
    client_id = 1 # Alpha
    setting_a = link_client_via_service(session, camp_a.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })
    setting_a_id = setting_a.id
    camp_b_id = camp_b.id
    update_payload = {"status": "inactive"}

    # Act: Try update Setting A via Campaign B's endpoint
    response = logged_in_client.put(f'/api/seller/campaigns/{camp_b_id}/clients/{setting_a_id}', json=update_payload)

    # Assert: Route catches ResourceNotFound (setting not found *for this campaign*)
    assert response.status_code == 404


# --- Test DELETE /api/seller/campaigns/{campaign_id}/clients/{setting_id} ---

def test_seller_remove_client_link_success(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign and setting link
    WHEN DELETE /api/seller/campaigns/{cid}/clients/{sid}
    THEN check status 204 No Content and link removed.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Remove Link Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    client_id = 1 # Alpha
    setting = link_client_via_service(session, campaign.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })
    campaign_id = campaign.id
    setting_id = setting.id
    assert session.get(CampaignClientSettingsModel, setting_id) is not None # Verify exists

    # Act: Call API (handles commit)
    response = logged_in_client.delete(f'/api/seller/campaigns/{campaign_id}/clients/{setting_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database
    assert session.get(CampaignClientSettingsModel, setting_id) is None


def test_seller_remove_client_link_fail_not_found(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign
    WHEN DELETE /api/seller/campaigns/{cid}/clients/{sid} for non-existent setting ID
    THEN check status 404 Not Found.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = create_campaign_via_service(session, seller_id, "Remove Missing Setting Camp P5", routing_strategy="priority", dial_timeout_seconds=30)
    campaign_id = campaign.id

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{campaign_id}/clients/999999')

    # Assert: Route catches ResourceNotFound
    assert response.status_code == 404


def test_seller_remove_client_link_fail_wrong_campaign(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaigns A & B, setting exists for camp A
    WHEN DELETE /api/seller/campaigns/{camp_B_id}/clients/{setting_A_id}
    THEN check status 404 Not Found.
    """
    # Arrange
    seller_id = get_seller_id(session)
    camp_a = create_campaign_via_service(session, seller_id, "Remove Wrong Camp A P5", routing_strategy="priority", dial_timeout_seconds=30)
    camp_b = create_campaign_via_service(session, seller_id, "Remove Wrong Camp B P5", routing_strategy="priority", dial_timeout_seconds=30)
    client_id = 1 # Alpha
    setting_a = link_client_via_service(session, camp_a.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })
    setting_a_id = setting_a.id
    camp_b_id = camp_b.id

    # Act: Try delete Setting A via Campaign B's endpoint
    response = logged_in_client.delete(f'/api/seller/campaigns/{camp_b_id}/clients/{setting_a_id}')

    # Assert: Route catches ResourceNotFound (setting not found *for this campaign*)
    assert response.status_code == 404
