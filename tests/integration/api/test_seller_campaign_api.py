# -*- coding: utf-8 -*-
"""
Integration tests for Seller Campaign Management endpoints (/api/seller/campaigns).
"""
import json
import pytest

# Import Models for DB checks and setup helpers
from app.database.models import CampaignModel, UserModel, DidModel, ClientModel, CampaignDidModel, CampaignClientSettingsModel
# Import Services for potential setup if needed (though API calls preferred)
from app.services.campaign_service import CampaignService
from app.services.user_service import UserService
from app.services.did_service import DidService
from app.services.client_service import ClientService

# Fixtures: client, session, db, logged_in_client (seller), logged_in_admin_client

# Helper to get seller ID
def get_seller_id(session):
    user = session.query(UserModel).filter_by(username="pytest_seller").one_or_none()
    assert user is not None, "Test setup failed: pytest_seller not found."
    return user.id

def get_admin_id(session):
    user = session.query(UserModel).filter_by(username="pytest_admin").one_or_none()
    if user is None:
         pytest.fail("FATAL: pytest_admin user not found. Check logged_in_admin_client fixture setup.")
    return user.id
# --- Test GET /api/seller/campaigns ---

def test_seller_get_own_campaigns_list(logged_in_client, session):
    """
    GIVEN seller client logged in and seller owns campaigns
    WHEN GET /api/seller/campaigns is requested
    THEN check status 200 and only own campaigns are returned (paginated).
    """
    # Arrange: Ensure the seller owns campaigns
    seller_id = get_seller_id(session)
    camp1 = CampaignService.create_campaign(seller_id, "My First Camp", "priority", 30)
    camp2 = CampaignService.create_campaign(seller_id, "My Second Camp", "round_robin", 25, status='inactive')
    # Create campaign for another user (should not appear)
    other_user = UserService.create_user("otherseller_camp", "other_camp@s.com", "Pass123")
    CampaignService.create_campaign(other_user.id, "Other Seller Camp", "priority", 30)
    # No commit needed - relying on fixture rollback and API call visibility

    # Act
    response = logged_in_client.get('/api/seller/campaigns?page=1&per_page=5')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 2 # Only the 2 created for pytest_seller
    assert len(data['items']) == 2
    assert data.get('perPage') == 5 # Check camelCase key
    names_returned = {item['name'] for item in data['items']}
    assert camp1.name in names_returned
    assert camp2.name in names_returned
    assert "Other Seller Camp" not in names_returned
    # List view shouldn't contain nested details by default schema config
    assert 'dids' not in data['items'][0]
    assert 'clientSettings' not in data['items'][0]

def test_seller_get_campaigns_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/seller/campaigns is requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/seller/campaigns')
    assert response.status_code == 401


# --- Test POST /api/seller/campaigns ---

def test_seller_create_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/campaigns with valid data
    THEN check status 201 Created and campaign is added to DB for that seller.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign_payload = {
        "name": "Seller Created Campaign",
        "routingStrategy": "weighted", # Use camelCase matching schema data_key
        "dialTimeoutSeconds": 28,   # Use camelCase matching schema data_key
        "description": "Created via API test",
        "status": "active"
    }

    # Act
    response = logged_in_client.post('/api/seller/campaigns', json=campaign_payload)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['name'] == campaign_payload['name']
    assert data['routingStrategy'] == campaign_payload['routingStrategy']
    assert data['dialTimeoutSeconds'] == campaign_payload['dialTimeoutSeconds']
    assert data['status'] == campaign_payload['status']
    assert data['description'] == campaign_payload['description']
    assert data.get('dids', []) == []
    assert data.get('clientSettings', []) == []
    assert 'id' in data
    campaign_id = data['id']

    # Assert Database State
    campaign_db = session.get(CampaignModel, campaign_id)
    assert campaign_db is not None
    assert campaign_db.user_id == seller_id # Check ownership
    assert campaign_db.name == campaign_payload['name']
    assert campaign_db.routing_strategy == campaign_payload['routingStrategy'] # DB stores snake_case
    assert campaign_db.dial_timeout_seconds == campaign_payload['dialTimeoutSeconds'] # DB stores snake_case


def test_seller_create_campaign_duplicate_name_fail(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign with a specific name
    WHEN POST /api/seller/campaigns with the same name
    THEN check status 409 Conflict.
    """
    # Arrange: Create initial campaign
    seller_id = get_seller_id(session)
    existing_name = "Duplicate Campaign Name Test"
    CampaignService.create_campaign(seller_id, existing_name, "priority", 30)

    campaign_payload = {
        "name": existing_name, # Duplicate name
        "routingStrategy": "round_robin",
        "dialTimeoutSeconds": 20
    }

    # Act
    response = logged_in_client.post('/api/seller/campaigns', json=campaign_payload)

    # Assert
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Campaign name '{existing_name}' already exists" in data.get('message', '')


def test_seller_create_campaign_missing_name(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/campaigns without 'name'
    THEN check status 400 Bad Request.
    """
    campaign_payload = {
        # Missing name
        "routingStrategy": "priority",
        "dialTimeoutSeconds": 25
    }
    response = logged_in_client.post('/api/seller/campaigns', json=campaign_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'name' in data.get('errors', {})


def test_seller_create_campaign_invalid_strategy(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN POST /api/seller/campaigns with invalid 'routingStrategy'
    THEN check status 400 Bad Request.
    """
    campaign_payload = {
        "name": "Invalid Strategy Camp Test",
        "routingStrategy": "fastest", # Invalid value
        "dialTimeoutSeconds": 25
    }
    response = logged_in_client.post('/api/seller/campaigns', json=campaign_payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'routingStrategy' in data.get('errors', {})

def test_seller_get_own_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign
    WHEN GET /api/seller/campaigns/{campaign_id} is requested
    THEN check status 200 OK and full campaign details are returned.
    """
    # Arrange: Create campaign via service
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Get My Campaign", "priority", 30)
    did = DidService.add_did(seller_id, "+15553334444")
    client1 = session.get(ClientModel, 1) # Assume client 1 exists

    # Call services to create links (they add to session, don't commit)
    CampaignService.set_campaign_dids(campaign.id, seller_id, [did.id])
    setting1 = None
    if client1:
        setting1 = CampaignService.add_client_to_campaign(campaign.id, seller_id, client1.id, {
            "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
        })
    else:
        print("WARN: Client ID 1 not found, skipping client link setup...")

    # Commit the changes made during setup within this test's transaction
    session.commit() # <--- ADD COMMIT HERE
    target_id = campaign.id # Get ID after potential flush/commit

    # Debugging: Check campaign state after commit
    session.refresh(campaign)  # Ensure latest state
    print(f"DEBUG: Campaign {target_id} DIDs: {campaign.dids}")
    print(f"DEBUG: Campaign {target_id} DID Associations: {campaign.did_associations}")

    # Act
    response = logged_in_client.get(f'/api/seller/campaigns/{target_id}')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['name'] == "Get My Campaign"
    assert data['routingStrategy'] == "priority"
    assert isinstance(data.get('dids'), list)
    assert isinstance(data.get('clientSettings'), list)

    # Check nested data (should now be visible after commit)
    if did:
        assert len(data['dids']) == 1, f"Expected 1 DID, found {len(data['dids'])}"
        assert data['dids'][0]['id'] == did.id
    if client1 and setting1: # Check if client link was successfully made and committed
        assert len(data['clientSettings']) == 1, f"Expected 1 ClientSetting, found {len(data['clientSettings'])}"
        assert data['clientSettings'][0]['id'] == setting1.id # Check the setting ID
        assert data['clientSettings'][0]['client']['id'] == client1.id
    elif client1 and not setting1:
        pytest.fail("Client link setup failed unexpectedly.")

def test_seller_get_other_campaign_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/campaigns/{campaign_id} for a campaign owned by another user
    THEN check status 404 Not Found.
    """
    # Arrange: Create campaign for another user
    other_user = UserService.create_user("otherseller_camp2", "other_camp2@s.com", "Pass123")
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Seller Camp 2", "priority", 30)
    target_id = other_campaign.id

    # Act
    response = logged_in_client.get(f'/api/seller/campaigns/{target_id}')

    # Assert
    assert response.status_code == 404
    data = json.loads(response.data)
    assert f"Campaign with ID {target_id} not found or not owned by user" in data.get('message', '')


def test_seller_get_nonexistent_campaign_fail(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/campaigns/{campaign_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_client.get('/api/seller/campaigns/99999')
    assert response.status_code == 404


# --- Test PUT /api/seller/campaigns/{campaign_id} ---

def test_seller_update_own_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign
    WHEN PUT /api/seller/campaigns/{campaign_id} with valid update data
    THEN check status 200 OK and campaign is updated.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Update Campaign Test", "priority", 30, status="active")
    target_id = campaign.id
    update_payload = {
        "name": "Update Campaign Test (Updated)",
        "routingStrategy": "round_robin",
        "status": "paused",
        "dialTimeoutSeconds": 45
    }

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{target_id}', json=update_payload)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['name'] == update_payload['name']
    assert data['routingStrategy'] == update_payload['routingStrategy']
    assert data['status'] == update_payload['status']
    assert data['dialTimeoutSeconds'] == update_payload['dialTimeoutSeconds']

    # Assert Database
    session.refresh(campaign) # Refresh object after API commit
    assert campaign.name == update_payload['name']
    assert campaign.routing_strategy == update_payload['routingStrategy'] # DB uses snake_case
    assert campaign.status == update_payload['status']
    assert campaign.dial_timeout_seconds == update_payload['dialTimeoutSeconds'] # DB uses snake_case


def test_seller_update_other_campaign_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN PUT /api/seller/campaigns/{campaign_id} for another user's campaign
    THEN check status 403 Forbidden or 404 Not Found.
    """
    # Arrange
    other_user = UserService.create_user("otherseller_camp3", "other_camp3@s.com", "Pass123")
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Seller Camp 3", "priority", 30)
    target_id = other_campaign.id
    update_payload = {"name": "Attempted Update"}

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{target_id}', json=update_payload)

    # Assert (Service check should result in 403/404)
    assert response.status_code in [403, 404]


def test_seller_update_campaign_duplicate_name_fail(logged_in_client, session):
    """
    GIVEN seller client logged in and owns two campaigns
    WHEN PUT /api/seller/campaigns/{id} tries to rename one to match the other
    THEN check status 409 Conflict.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign1 = CampaignService.create_campaign(seller_id, "Unique Name 1", "priority", 30)
    campaign2 = CampaignService.create_campaign(seller_id, "Unique Name 2", "priority", 30)
    update_payload = {"name": campaign1.name} # Try renaming campaign2 to campaign1's name

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign2.id}', json=update_payload)

    # Assert
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Campaign name '{campaign1.name}' already exists" in data.get('message', '')


# --- Test DELETE /api/seller/campaigns/{campaign_id} ---

def test_seller_delete_own_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign (with links)
    WHEN DELETE /api/seller/campaigns/{campaign_id} is requested
    THEN check status 204 No Content and campaign + links are removed.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Delete Campaign Test", "priority", 30)
    did = DidService.add_did(seller_id, "+15554445555")
    client1 = session.get(ClientModel, 1) # Assume client 1 exists
    # Add links
    CampaignService.set_campaign_dids(campaign.id, seller_id, [did.id])
    setting1 = None
    if client1:
        setting1 = CampaignService.add_client_to_campaign(campaign.id, seller_id, client1.id, {
             "max_concurrency": 2, "forwarding_priority": 0, "weight": 100
         })
    # Get IDs before delete
    target_id = campaign.id
    did_link_exists_before = session.query(CampaignDidModel).filter_by(campaign_id=target_id, did_id=did.id).one_or_none()
    setting_link_exists_before = session.get(CampaignClientSettingsModel, setting1.id) if setting1 else None

    assert session.get(CampaignModel, target_id) is not None
    assert did_link_exists_before is not None
    if setting1: assert setting_link_exists_before is not None

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database (Check campaign and links are gone due to cascade)
    assert session.get(CampaignModel, target_id) is None
    assert session.query(CampaignDidModel).filter_by(campaign_id=target_id).count() == 0
    assert session.query(CampaignClientSettingsModel).filter_by(campaign_id=target_id).count() == 0


def test_seller_delete_other_campaign_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN DELETE /api/seller/campaigns/{campaign_id} for another user's campaign
    THEN check status 403 Forbidden or 404 Not Found.
    """
    # Arrange
    other_user = UserService.create_user("otherseller_camp4", "other_camp4@s.com", "Pass123")
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Seller Camp 4", "priority", 30)
    target_id = other_campaign.id

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{target_id}')

    # Assert (Service check should result in 403/404)
    assert response.status_code in [403, 404]

def test_seller_get_own_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign with links
    WHEN GET /api/seller/campaigns/{campaign_id} is requested
    THEN check status 200 OK and full campaign details (incl links) are returned.
    """
    # Arrange: Create campaign, DID, Client link via service
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Get Detailed Campaign", "priority", 30)
    did = DidService.add_did(seller_id, "+15553334444")
    client1 = session.get(ClientModel, 1) # Assume client 1 ('client_alpha_sales') exists from sample data
    assert client1 is not None, "Client ID 1 not found in sample data setup"

    # Call services to create links - they DO NOT commit
    CampaignService.set_campaign_dids(campaign.id, seller_id, [did.id])
    setting1 = CampaignService.add_client_to_campaign(campaign.id, seller_id, client1.id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })

    # Commit the setup within this test's transaction
    session.commit()
    target_id = campaign.id # Get ID after potential flush/commit

    # Act
    response = logged_in_client.get(f'/api/seller/campaigns/{target_id}')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['name'] == "Get Detailed Campaign"
    assert isinstance(data.get('dids'), list)
    assert isinstance(data.get('clientSettings'), list)
    assert len(data['dids']) == 1, f"Expected 1 DID, found {len(data.get('dids', []))}"
    assert data['dids'][0]['id'] == did.id
    assert len(data['clientSettings']) == 1, f"Expected 1 ClientSetting, found {len(data.get('clientSettings', []))}"
    assert data['clientSettings'][0]['id'] == setting1.id
    assert data['clientSettings'][0]['client']['id'] == client1.id

def test_seller_get_other_campaign_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/campaigns/{campaign_id} for another user's campaign
    THEN check status 404 Not Found.
    """
    # Arrange: Create campaign for another user
    other_user = UserService.create_user("otherseller_camp2", "other_camp2@s.com", "Pass123")
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Seller Camp 2", "priority", 30)
    session.commit() # Commit the other user's campaign
    target_id = other_campaign.id

    # Act
    response = logged_in_client.get(f'/api/seller/campaigns/{target_id}')

    # Assert
    assert response.status_code == 404
    data = json.loads(response.data)
    assert f"Campaign with ID {target_id} not found or not owned by user" in data.get('message', '')


def test_seller_get_nonexistent_campaign_fail(logged_in_client):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/campaigns/{campaign_id} for non-existent ID
    THEN check status 404 Not Found.
    """
    response = logged_in_client.get('/api/seller/campaigns/99999')
    assert response.status_code == 404


# --- Test PUT /api/seller/campaigns/{campaign_id} ---

def test_seller_update_own_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign
    WHEN PUT /api/seller/campaigns/{campaign_id} with valid update data
    THEN check status 200 OK and campaign is updated.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Update Campaign Test", "priority", 30, status="active")
    session.commit() # Commit initial campaign
    target_id = campaign.id
    update_payload = {
        "name": "Update Campaign Test (Updated)",
        "routingStrategy": "round_robin",
        "status": "paused",
        "dialTimeoutSeconds": 45
    }

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{target_id}', json=update_payload)

    # Assert Response
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == target_id
    assert data['name'] == update_payload['name']
    assert data['routingStrategy'] == update_payload['routingStrategy']
    assert data['status'] == update_payload['status']
    assert data['dialTimeoutSeconds'] == update_payload['dialTimeoutSeconds']

    # Assert Database
    # Re-fetch or refresh AFTER the API call (which includes commit)
    updated_campaign_db = session.get(CampaignModel, target_id)
    assert updated_campaign_db.name == update_payload['name']
    assert updated_campaign_db.routing_strategy == update_payload['routingStrategy'] # DB stores snake_case
    assert updated_campaign_db.status == update_payload['status']
    assert updated_campaign_db.dial_timeout_seconds == update_payload['dialTimeoutSeconds'] # DB stores snake_case


def test_seller_update_other_campaign_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN PUT /api/seller/campaigns/{campaign_id} for another user's campaign
    THEN check status 403 Forbidden or 404 Not Found.
    """
    # Arrange
    other_user = UserService.create_user("otherseller_camp3", "other_camp3@s.com", "Pass123")
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Seller Camp 3", "priority", 30)
    session.commit()
    target_id = other_campaign.id
    update_payload = {"name": "Attempted Update"}

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{target_id}', json=update_payload)

    # Assert (Service check should result in 403/404)
    assert response.status_code in [403, 404]


def test_seller_update_campaign_duplicate_name_fail(logged_in_client, session):
    """
    GIVEN seller client logged in and owns two campaigns
    WHEN PUT /api/seller/campaigns/{id} tries to rename one to match the other
    THEN check status 409 Conflict.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign1 = CampaignService.create_campaign(seller_id, "Unique Name Camp 1", "priority", 30)
    campaign2 = CampaignService.create_campaign(seller_id, "Unique Name Camp 2", "priority", 30)
    session.commit()
    update_payload = {"name": campaign1.name} # Try renaming campaign2 to campaign1's name

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign2.id}', json=update_payload)

    # Assert
    assert response.status_code == 409
    data = json.loads(response.data)
    assert f"Campaign name '{campaign1.name}' already exists" in data.get('message', '')


# --- Test DELETE /api/seller/campaigns/{campaign_id} ---

def test_seller_delete_own_campaign_success(logged_in_client, session):
    """
    GIVEN seller client logged in and owns a campaign (with links)
    WHEN DELETE /api/seller/campaigns/{campaign_id} is requested
    THEN check status 204 No Content and campaign + links are removed.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Delete Campaign Test", "priority", 30)
    did = DidService.add_did(seller_id, "+15554445555")
    client1 = session.get(ClientModel, 1)
    assert client1 is not None, "Client ID 1 not found"
    # Add links using service (no commit in service)
    CampaignService.set_campaign_dids(campaign.id, seller_id, [did.id])
    setting1 = CampaignService.add_client_to_campaign(campaign.id, seller_id, client1.id, {
         "max_concurrency": 2, "forwarding_priority": 0, "weight": 100
    })
    session.commit() # Commit setup
    target_id = campaign.id
    setting1_id = setting1.id # Get ID after commit/flush

    # Verify records exist before delete
    assert session.get(CampaignModel, target_id) is not None
    assert session.query(CampaignDidModel).filter_by(campaign_id=target_id, did_id=did.id).one_or_none() is not None
    assert session.get(CampaignClientSettingsModel, setting1_id) is not None

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{target_id}')

    # Assert Response
    assert response.status_code == 204

    # Assert Database (Check campaign and links are gone due to cascade)
    assert session.get(CampaignModel, target_id) is None
    assert session.query(CampaignDidModel).filter_by(campaign_id=target_id).count() == 0
    assert session.query(CampaignClientSettingsModel).filter_by(campaign_id=target_id).count() == 0


def test_seller_delete_other_campaign_fail(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN DELETE /api/seller/campaigns/{campaign_id} for another user's campaign
    THEN check status 403 Forbidden or 404 Not Found.
    """
    # Arrange
    other_user = UserService.create_user("otherseller_camp4", "other_camp4@s.com", "Pass123")
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Seller Camp 4", "priority", 30)
    session.commit()
    target_id = other_campaign.id

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{target_id}')

    # Assert (Service check should result in 403/404)
    assert response.status_code in [403, 404]


def test_seller_set_campaign_dids_success(logged_in_client, session):
    """
    GIVEN seller logged in, owns campaign and DIDs
    WHEN PUT /api/seller/campaigns/{id}/dids with valid owned DID IDs
    THEN check status 200 OK and links are updated in DB.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Set DIDs Camp", "priority", 30)
    did1 = DidService.add_did(seller_id, "+15550101010")
    did2 = DidService.add_did(seller_id, "+15550101011")
    did3 = DidService.add_did(seller_id, "+15550101012") # Unused initially
    # Add an initial link to remove later
    CampaignService.set_campaign_dids(campaign.id, seller_id, [did1.id])
    session.commit() # Commit setup state
    campaign_id = campaign.id

    # Act: Replace link to did1 with links to did2 and did3
    payload = {"didIds": [did2.id, did3.id]}
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json=payload)

    # Assert Response
    assert response.status_code == 200
    assert "updated successfully" in json.loads(response.data).get('message', '')

    # Assert Database state
    links = session.query(CampaignDidModel).filter_by(campaign_id=campaign_id).all()
    linked_did_ids = {link.did_id for link in links}
    assert len(links) == 2
    assert did1.id not in linked_did_ids # Should be removed
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
    campaign = CampaignService.create_campaign(seller_id, "Clear DIDs Camp", "priority", 30)
    did1 = DidService.add_did(seller_id, "+15550202020")
    CampaignService.set_campaign_dids(campaign.id, seller_id, [did1.id])
    session.commit()
    campaign_id = campaign.id
    assert session.query(CampaignDidModel).filter_by(campaign_id=campaign_id).count() == 1 # Verify initial state

    # Act: Send empty list
    payload = {"didIds": []}
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json=payload)

    # Assert Response
    assert response.status_code == 200

    # Assert Database state
    assert session.query(CampaignDidModel).filter_by(campaign_id=campaign_id).count() == 0


def test_seller_set_campaign_dids_fail_did_not_owned(logged_in_client, session):
    """
    GIVEN seller logged in, owns campaign
    WHEN PUT /api/seller/campaigns/{id}/dids includes a DID ID not owned by seller
    THEN check status 400/403 Bad Request/Forbidden.
    """
     # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Not Owned DID Camp", "priority", 30)
    # Create DID owned by another user
    other_user = UserService.create_user("otherseller_didlink", "other_link@s.com", "Pass123")
    other_did = DidService.add_did(user_id=other_user.id, number="+15550303030")
    session.commit()
    campaign_id = campaign.id

    # Act: Try to link other user's DID
    payload = {"didIds": [other_did.id]}
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/dids', json=payload)

    # Assert
    assert response.status_code in [400, 403] # Service might raise ValueError (400) or AuthorizationError (403)
    assert "not owned by the user" in json.loads(response.data).get('message', '')


def test_seller_set_campaign_dids_fail_campaign_not_owned(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN PUT /api/seller/campaigns/{id}/dids for a campaign owned by another user
    THEN check status 404 Not Found.
    """
    # Arrange
    seller_id = get_seller_id(session)
    my_did = DidService.add_did(seller_id, "+15550404040") # A DID owned by the logged-in user
    # Campaign owned by other user
    other_user = UserService.create_user("otherseller_didlink2", "other_link2@s.com", "Pass123")
    other_campaign = CampaignService.create_campaign(other_user.id, "Other User Set DID Camp", "priority", 30)
    # No commit needed - transaction managed by session fixture

    # Flush to get IDs if needed
    session.flush()
    other_campaign_id = other_campaign.id
    my_did_id = my_did.id # Get the DID ID after flush

    # Define the payload for the API call
    payload = {"didIds": [my_did_id]} # Use the actual ID

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{other_campaign_id}/dids', json=payload)

    # Assert
    assert response.status_code == 404 # Status is correct
    data = json.loads(response.data)
    # Check for the "not authorized" part of the message, as that's what the service raises first
    assert f"User {seller_id} not authorized for campaign {other_campaign_id}" in data.get('message', '') # <<< CORRECTED Assertion Message Check

# --- Test GET /api/seller/campaigns/available_clients ---

def test_seller_get_available_clients(logged_in_client, session):
    """
    GIVEN seller client logged in
    WHEN GET /api/seller/campaigns/available_clients
    THEN check status 200 OK and active clients are listed.
    """
    # Arrange:
    # 1. Ensure the 'pytest_admin' user exists (created by its fixture if needed by another test, or create here)
    admin_user = session.query(UserModel).filter_by(username="pytest_admin").one_or_none()
    if not admin_user:
         admin_user = UserService.create_user(
             username="pytest_admin", email="pytest@admin.test", password="PytestAdminPass123!", role="admin"
         )
         # No commit needed, part of the test transaction

    admin_id = admin_user.id

    # 2. Create an inactive client using the admin_id
    # Use ClientService, assumes create_client_with_pjsip doesn't commit
    ClientService.create_client_with_pjsip(admin_id,
        {"client_identifier": "inactive_test", "name": "Inactive Test", "status": "inactive"},
        {"endpoint": {"id": "inactive_test", "context": "ctx"}, "aor": {"id": "inactive_test", "contact": "sip:inactive"}}
    )
    # No commit needed here, will be rolled back by session fixture

    # Act: Use the seller client provided by logged_in_client
    response = logged_in_client.get('/api/seller/campaigns/available_clients')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert isinstance(data, list)
    assert len(data) >= 3 # At least alpha, beta, gamma from sample
    # Check identifiers and absence of inactive one
    identifiers = {item['clientIdentifier'] for item in data}
    assert 'client_alpha_sales' in identifiers
    assert 'client_beta_support' in identifiers
    assert 'client_gamma_intake' in identifiers
    assert 'inactive_test' not in identifiers
    # Check schema includes only expected fields
    assert 'id' in data[0]
    assert 'name' in data[0]
    assert 'department' in data[0]
    assert 'clientIdentifier' in data[0]
    assert 'status' not in data[0] # Should only list active ones
    assert 'pjsipEndpoint' not in data[0] # Excluded by simple schema


# --- Test POST /api/seller/campaigns/{campaign_id}/clients ---

def test_seller_add_client_link_success(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign, client exists
    WHEN POST /api/seller/campaigns/{id}/clients with valid settings
    THEN check status 201 Created and link is added.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Link Client Camp", "priority", 30)
    client_id = 2 # Use Client Beta (ID 2 from sample data)
    session.commit()
    campaign_id = campaign.id
    settings_payload = {
        "clientId": client_id,
        "maxConcurrency": 7,
        "totalCallsAllowed": 500,
        "forwardingPriority": 1,
        "weight": 150,
        "status": "active"
    }

    # Act
    response = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings_payload)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['client']['id'] == client_id
    assert data['maxConcurrency'] == settings_payload['maxConcurrency']
    assert data['totalCallsAllowed'] == settings_payload['totalCallsAllowed']
    assert data['forwardingPriority'] == settings_payload['forwardingPriority']
    assert data['weight'] == settings_payload['weight']
    assert data['status'] == settings_payload['status']
    assert 'id' in data
    setting_id = data['id']

    # Assert Database
    setting_db = session.get(CampaignClientSettingsModel, setting_id)
    assert setting_db is not None
    assert setting_db.campaign_id == campaign_id
    assert setting_db.client_id == client_id
    assert setting_db.max_concurrency == settings_payload['maxConcurrency']

def test_seller_add_client_link_duplicate_fail(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign, client is already linked
    WHEN POST /api/seller/campaigns/{id}/clients for the same client
    THEN check status 409 Conflict.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Duplicate Link Camp", "priority", 30)
    client_id = 1 # Alpha
    # Link it first
    CampaignService.add_client_to_campaign(campaign.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })
    session.commit()
    campaign_id = campaign.id
    # Payload to add the same client again
    settings_payload = {"clientId": client_id, "maxConcurrency": 1, "forwardingPriority": 1, "weight": 1}

    # Act
    response = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings_payload)

    # Assert
    assert response.status_code == 409
    assert f"Client {client_id} is already linked" in json.loads(response.data).get('message', '')

def test_seller_add_client_link_missing_settings(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign, client exists
    WHEN POST /api/seller/campaigns/{id}/clients missing required settings
    THEN check status 400 Bad Request.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Missing Settings Camp", "priority", 30)
    client_id = 1 # Alpha
    session.commit()
    campaign_id = campaign.id
    # Missing maxConcurrency, priority, weight
    settings_payload = {"clientId": client_id}

    # Act
    response = logged_in_client.post(f'/api/seller/campaigns/{campaign_id}/clients', json=settings_payload)

    # Assert
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'maxConcurrency' in data.get('errors', {})
    assert 'forwardingPriority' in data.get('errors', {})
    assert 'weight' in data.get('errors', {})


# --- Test PUT /api/seller/campaigns/{campaign_id}/clients/{setting_id} ---

def test_seller_update_client_setting_success(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign and setting link
    WHEN PUT /api/seller/campaigns/{cid}/clients/{sid} with valid updates
    THEN check status 200 OK and settings are updated.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Update Setting Camp", "priority", 30)
    client_id = 1 # Alpha
    setting = CampaignService.add_client_to_campaign(campaign.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100, "status": "active"
    })
    session.commit()
    campaign_id = campaign.id
    setting_id = setting.id
    update_payload = {
        "maxConcurrency": 8,
        "status": "inactive",
        "forwardingPriority": 10
    } # Partial update

    # Act
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
    session.refresh(setting)
    assert setting.max_concurrency == 8
    assert setting.status == "inactive"
    assert setting.forwarding_priority == 10
    assert setting.weight == 100


def test_seller_update_client_setting_fail_not_found(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign
    WHEN PUT /api/seller/campaigns/{cid}/clients/{sid} for non-existent setting ID
    THEN check status 404 Not Found.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Update Missing Setting Camp", "priority", 30)
    session.commit()
    campaign_id = campaign.id
    update_payload = {"status": "inactive"}

    # Act
    response = logged_in_client.put(f'/api/seller/campaigns/{campaign_id}/clients/99999', json=update_payload)

    # Assert
    assert response.status_code == 404


def test_seller_update_client_setting_fail_wrong_campaign(logged_in_client, session):
    """
    GIVEN seller client logged in, owns two campaigns, setting exists for camp A
    WHEN PUT /api/seller/campaigns/{camp_B_id}/clients/{setting_A_id}
    THEN check status 404 Not Found (setting not found for *this* campaign).
    """
    # Arrange
    seller_id = get_seller_id(session)
    camp_a = CampaignService.create_campaign(seller_id, "Update Wrong Camp A", "priority", 30)
    camp_b = CampaignService.create_campaign(seller_id, "Update Wrong Camp B", "priority", 30)
    client_id = 1 # Alpha
    setting_a = CampaignService.add_client_to_campaign(camp_a.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })
    session.commit()
    setting_a_id = setting_a.id
    camp_b_id = camp_b.id
    update_payload = {"status": "inactive"}

    # Act: Try to update Setting A via Campaign B's endpoint
    response = logged_in_client.put(f'/api/seller/campaigns/{camp_b_id}/clients/{setting_a_id}', json=update_payload)

    # Assert
    assert response.status_code == 404
    assert f"Setting {setting_a_id} not found for campaign {camp_b_id}" in json.loads(response.data).get('message', '')


# --- Test DELETE /api/seller/campaigns/{campaign_id}/clients/{setting_id} ---

def test_seller_remove_client_link_success(logged_in_client, session):
    """
    GIVEN seller client logged in, owns campaign and setting link
    WHEN DELETE /api/seller/campaigns/{cid}/clients/{sid}
    THEN check status 204 No Content and link is removed.
    """
    # Arrange
    seller_id = get_seller_id(session)
    campaign = CampaignService.create_campaign(seller_id, "Remove Link Camp", "priority", 30)
    client_id = 1 # Alpha
    setting = CampaignService.add_client_to_campaign(campaign.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })
    session.commit()
    campaign_id = campaign.id
    setting_id = setting.id
    assert session.get(CampaignClientSettingsModel, setting_id) is not None # Verify exists

    # Act
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
    campaign = CampaignService.create_campaign(seller_id, "Remove Missing Setting Camp", "priority", 30)
    session.commit()
    campaign_id = campaign.id

    # Act
    response = logged_in_client.delete(f'/api/seller/campaigns/{campaign_id}/clients/99999')

    # Assert
    assert response.status_code == 404


def test_seller_remove_client_link_fail_wrong_campaign(logged_in_client, session):
    """
    GIVEN seller client logged in, owns two campaigns, setting exists for camp A
    WHEN DELETE /api/seller/campaigns/{camp_B_id}/clients/{setting_A_id}
    THEN check status 404 Not Found.
    """
    # Arrange
    seller_id = get_seller_id(session)
    camp_a = CampaignService.create_campaign(seller_id, "Remove Wrong Camp A", "priority", 30)
    camp_b = CampaignService.create_campaign(seller_id, "Remove Wrong Camp B", "priority", 30)
    client_id = 1 # Alpha
    setting_a = CampaignService.add_client_to_campaign(camp_a.id, seller_id, client_id, {
        "max_concurrency": 5, "forwarding_priority": 0, "weight": 100
    })
    session.commit()
    setting_a_id = setting_a.id
    camp_b_id = camp_b.id

    # Act: Try to delete Setting A via Campaign B's endpoint
    response = logged_in_client.delete(f'/api/seller/campaigns/{camp_b_id}/clients/{setting_a_id}')

    # Assert
    assert response.status_code == 404
    assert f"Setting {setting_a_id} not found for campaign {camp_b_id}" in json.loads(response.data).get('message', '')