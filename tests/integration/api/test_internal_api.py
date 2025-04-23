# tests/integration/api/test_internal_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the Internal API endpoints (/api/internal/).
Requires INTERNAL_API_TOKEN to be set in config.
"""
import json
import pytest
import logging
from datetime import datetime, timedelta, timezone

# Import necessary components
from app.extensions import db
from app.database.models import CallLogModel, CampaignClientSettingsModel, UserModel, CampaignModel, DidModel, ClientModel
from app.services.user_service import UserService
from app.services.did_service import DidService
from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService

log = logging.getLogger(__name__)

# Fixtures: client, session, db, app (for config access)

# --- Test Data Setup Helper ---
# (Similar helper as in test_seller_log_api, but maybe slightly different needs)
def create_internal_log_payload(status="ANSWERED", offset_days=0, unique_suffix=""):
    """Creates a sample payload dictionary for the log_call endpoint."""
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=offset_days)
    # Ensure unique ID for different calls within a test run
    ts_part = start_time.strftime('%Y%m%d%H%M%S%f')
    unique_id = f"int-test-{ts_part}-{unique_suffix}"
    linked_id = f"int-linked-{ts_part}-{unique_suffix}"

    payload = {
        "incomingDidNumber": "+1INTERNALDID",
        "timestampStart": start_time.isoformat(),
        "callStatus": status,
        "asteriskUniqueid": unique_id,
        "asteriskLinkedid": linked_id,
        "callerIdNum": "+1INTERNALCALLER",
        "timestampEnd": (start_time + timedelta(seconds=60)).isoformat(),
        "durationSeconds": 60,
        # Nullable fields can be omitted or set to None
        "userId": None,
        "campaignId": None,
        "didId": None,
        "clientId": None,
        "campaignClientSettingId": None,
        "timestampAnswered": None,
        "billsecSeconds": 0,
        "hangupCauseCode": 16,
        "hangupCauseText": "Normal Clearing",
    }
    if status == "ANSWERED":
        payload["timestampAnswered"] = (start_time + timedelta(seconds=5)).isoformat()
        payload["billsecSeconds"] = 55
    return payload

# --- Fixture for Setting up necessary related data ---
@pytest.fixture(scope="function")
def internal_api_setup(session):
    """
    Sets up/Retrieves User, Campaign, DID, Client, Setting for log tests.
    Checks for existing entities before creating to handle persistent state across tests.
    """
    log.debug("Setting up/Retrieving internal_api_setup fixture data...")
    returned_data = {}
    try:
        # --- Get or Create User (Seller) ---
        user = session.query(UserModel).filter_by(username="internal_seller").one_or_none()
        if not user:
            user = UserService.create_user("internal_seller", "internal@seller.test", "InternalPass1!")
            session.flush()
            log.info(f"Created user 'internal_seller' ID: {user.id}")
        returned_data["user_id"] = user.id

        # --- Get or Create DID ---
        did = session.query(DidModel).filter_by(number="+1INTERNALDID").one_or_none()
        if not did:
            did = DidService.add_did(user.id, "+1INTERNALDID")
            session.flush()
            log.info(f"Created DID '+1INTERNALDID' ID: {did.id}")
        # Ensure DID belongs to the correct user if found
        elif did.user_id != user.id:
             pytest.fail(f"Setup Error: DID +1INTERNALDID found but belongs to wrong user ({did.user_id} vs {user.id})")
        returned_data["did_id"] = did.id

        # --- Get or Create Client ---
        client_obj = session.query(ClientModel).filter_by(client_identifier="internal_client").one_or_none()
        if not client_obj:
            # Create Admin User if needed
            admin = session.query(UserModel).filter_by(username="internal_admin").one_or_none()
            if not admin:
                admin = UserService.create_user("internal_admin", "internal@admin.test", "InternalAdminPass1!", role="admin")
                session.flush()
                log.info(f"Created admin 'internal_admin' ID: {admin.id}")

            client_obj = ClientService.create_client_with_pjsip(
                admin.id,
                {"client_identifier": "internal_client", "name": "Internal Test Client"},
                { "endpoint": {"id": "internal_client", "context": "int-test", "aors": "internal_client"},
                  "aor": {"id": "internal_client", "contact": "sip:internal@test"} }
            )
            session.flush()
            log.info(f"Created client 'internal_client' ID: {client_obj.id}")
        returned_data["client_id"] = client_obj.id

        # --- Get or Create Campaign ---
        campaign = session.query(CampaignModel).filter_by(user_id=user.id, name="Internal Log Camp").one_or_none()
        if not campaign:
            campaign = CampaignService.create_campaign(user.id, "Internal Log Camp", "priority", 30)
            session.flush()
            log.info(f"Created campaign 'Internal Log Camp' ID: {campaign.id}")
        returned_data["campaign_id"] = campaign.id

        # --- Get or Create CampaignClientSetting ---
        setting = session.query(CampaignClientSettingsModel).filter_by(
            campaign_id=campaign.id, client_id=client_obj.id
        ).one_or_none()
        if not setting:
            setting = CampaignService.add_client_to_campaign(
                campaign.id, user.id, client_obj.id,
                {"max_concurrency": 2, "forwarding_priority": 0, "weight": 100, "total_calls_allowed": 10}
            )
            session.flush()
            log.info(f"Created setting link ID: {setting.id}")
        returned_data["setting_id"] = setting.id
        returned_data["initial_calls"] = setting.current_total_calls # Get current value

        log.info("Finished internal_api_setup fixture setup/retrieval.")
        yield returned_data

    except Exception as e:
        log.exception(f"Error during internal_api_setup: {e}")
        # No explicit rollback needed, session fixture handles it
        pytest.fail(f"Failed during internal_api_setup: {e}")


# --- Test /api/internal/log_call ---

def test_log_call_success_no_counter(client, app, session, internal_api_setup):
    """
    GIVEN valid payload for non-answered call and correct token
    WHEN POST /api/internal/log_call
    THEN check status 201, log created, counter NOT incremented.
    """
    token = app.config.get('INTERNAL_API_TOKEN')
    assert token, "INTERNAL_API_TOKEN not configured in app"
    headers = {'X-Internal-API-Token': token, 'Content-Type': 'application/json'}

    payload = create_internal_log_payload(status="NOANSWER", unique_suffix="nocount")
    # Populate IDs from setup fixture
    payload["userId"] = internal_api_setup["user_id"]
    payload["didId"] = internal_api_setup["did_id"]
    payload["campaignId"] = internal_api_setup["campaign_id"]
    # No client/setting ID as call wasn't routed/answered potentially

    # Act
    response = client.post('/api/internal/log_call', headers=headers, json=payload)

    # Assert Response
    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['status'] == 'success'
    assert 'cdrId' in data
    log_id = data['cdrId']

    # Assert Database Log
    log_db = session.get(CallLogModel, log_id)
    assert log_db is not None
    assert log_db.asterisk_uniqueid == payload['asteriskUniqueid']
    assert log_db.call_status == "NOANSWER"
    assert log_db.user_id == internal_api_setup["user_id"]
    assert log_db.did_id == internal_api_setup["did_id"]
    assert log_db.campaign_id == internal_api_setup["campaign_id"]
    assert log_db.client_id is None
    assert log_db.campaign_client_setting_id is None

    # Assert Counter Unchanged
    setting_db = session.get(CampaignClientSettingsModel, internal_api_setup['setting_id'])
    assert setting_db.current_total_calls == internal_api_setup['initial_calls'] # Should be 0


def test_log_call_success_with_counter(client, app, session, internal_api_setup):
    """
    GIVEN valid payload for ANSWERED call with setting ID and correct token
    WHEN POST /api/internal/log_call
    THEN check status 201, log created, counter IS incremented.
    """
    token = app.config.get('INTERNAL_API_TOKEN')
    headers = {'X-Internal-API-Token': token, 'Content-Type': 'application/json'}

    payload = create_internal_log_payload(status="ANSWERED", unique_suffix="count")
    # Populate IDs needed for counter logic
    payload["userId"] = internal_api_setup["user_id"]
    payload["didId"] = internal_api_setup["did_id"]
    payload["campaignId"] = internal_api_setup["campaign_id"]
    payload["clientId"] = internal_api_setup["client_id"]
    payload["campaignClientSettingId"] = internal_api_setup["setting_id"]

    # Act
    response = client.post('/api/internal/log_call', headers=headers, json=payload)

    # Assert Response
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['status'] == 'success'
    assert 'cdrId' in data
    log_id = data['cdrId']

    # Assert Database Log
    log_db = session.get(CallLogModel, log_id)
    assert log_db is not None
    assert log_db.asterisk_uniqueid == payload['asteriskUniqueid']
    assert log_db.call_status == "ANSWERED"
    assert log_db.user_id == internal_api_setup["user_id"]
    assert log_db.did_id == internal_api_setup["did_id"]
    assert log_db.campaign_id == internal_api_setup["campaign_id"]
    assert log_db.client_id == internal_api_setup["client_id"]
    assert log_db.campaign_client_setting_id == internal_api_setup["setting_id"]

    # Assert Counter Incremented
    setting_db = session.get(CampaignClientSettingsModel, internal_api_setup['setting_id'])
    # Refresh needed if counter was updated via raw SQL in service, but ORM update should reflect
    session.refresh(setting_db)
    assert setting_db.current_total_calls == internal_api_setup['initial_calls'] + 1


def test_log_call_fail_bad_token(client, app):
    """
    GIVEN valid payload but incorrect/missing token
    WHEN POST /api/internal/log_call
    THEN check status 401 Unauthorized.
    """
    headers = {'X-Internal-API-Token': 'invalid-token', 'Content-Type': 'application/json'}
    payload = create_internal_log_payload(status="ANSWERED", unique_suffix="badtoken")

    response = client.post('/api/internal/log_call', headers=headers, json=payload)
    assert response.status_code == 401

    # Test with missing header
    response_missing = client.post('/api/internal/log_call', json=payload) # No headers
    assert response_missing.status_code == 401


def test_log_call_fail_missing_data(client, app, session):
    """
    GIVEN payload missing required fields and correct token
    WHEN POST /api/internal/log_call
    THEN check status 400 Bad Request.
    """
    token = app.config.get('INTERNAL_API_TOKEN')
    headers = {'X-Internal-API-Token': token, 'Content-Type': 'application/json'}
    payload = create_internal_log_payload(status="ANSWERED", unique_suffix="missing")
    del payload['asteriskUniqueid'] # Remove a required field

    response = client.post('/api/internal/log_call', headers=headers, json=payload)

    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['status'] == 'error'
    assert 'errors' in data
    assert 'asteriskUniqueid' in data['errors']


def test_log_call_fail_duplicate_uniqueid(client, app, session, internal_api_setup):
    """
    GIVEN correct token and payload
    WHEN POST /api/internal/log_call twice with same asteriskUniqueid
    THEN check first succeeds (201), second fails (409).
    """
    token = app.config.get('INTERNAL_API_TOKEN')
    headers = {'X-Internal-API-Token': token, 'Content-Type': 'application/json'}
    payload = create_internal_log_payload(status="BUSY", unique_suffix="duplicate")
    payload["userId"] = internal_api_setup["user_id"] # Add necessary IDs

    # Act 1: Post first time (should succeed)
    response1 = client.post('/api/internal/log_call', headers=headers, json=payload)
    assert response1.status_code == 201
    log_id_1 = json.loads(response1.data)['cdrId']
    assert session.get(CallLogModel, log_id_1) is not None # Verify DB state after commit

    # Act 2: Post second time with same payload (same uniqueid)
    response2 = client.post('/api/internal/log_call', headers=headers, json=payload)

    # Assert 2: Should fail with 409 Conflict
    assert response2.status_code == 409
    data2 = json.loads(response2.data)
    assert "Duplicate Asterisk Unique ID" in data2.get('message', '')


# --- Test /api/internal/route_info (Basic Checks) ---

@pytest.mark.skip(reason="Routing logic shifted, /route_info endpoint may be deprecated or needs separate setup")
def test_route_info_success(client, app, session, internal_api_setup):
     """
     GIVEN a configured DID+Campaign+Client route and correct token
     WHEN GET /api/internal/route_info?did=...
     THEN check status 200 and valid routing info.
     """
     # This test requires more specific setup ensuring a route exists for "+1INTERNALDID"
     # based on internal_api_setup data. Let's assume it should route for now.
     token = app.config.get('INTERNAL_API_TOKEN')
     headers = {'X-Internal-API-Token': token}
     did_number = "+1INTERNALDID" # The DID created in setup

     # Act
     response = client.get(f'/api/internal/route_info?did={did_number}', headers=headers)

     # Assert
     assert response.status_code == 200
     data = json.loads(response.data)
     assert data['status'] == 'proceed'
     assert 'routingInfo' in data
     assert len(data['routingInfo']['targets']) > 0
     assert data['routingInfo']['targets'][0]['clientIdentifier'] == 'internal_client'

@pytest.mark.skip(reason="Routing logic shifted, /route_info endpoint may be deprecated or needs separate setup")
def test_route_info_fail_no_route(client, app, session):
    """
    GIVEN correct token but DID has no route configured
    WHEN GET /api/internal/route_info?did=...
    THEN check status 404 Not Found.
    """
    token = app.config.get('INTERNAL_API_TOKEN')
    headers = {'X-Internal-API-Token': token}
    did_number = "+1NONEXISTENTDID"

    # Act
    response = client.get(f'/api/internal/route_info?did={did_number}', headers=headers)

    # Assert
    assert response.status_code == 404
    data = json.loads(response.data)
    assert data['status'] == 'reject'
    assert data.get('rejectReason') == 'did_not_found' # Or similar reason from service

def test_route_info_fail_bad_token(client, app):
    """
    GIVEN invalid token
    WHEN GET /api/internal/route_info?did=...
    THEN check status 401 Unauthorized.
    """
    headers = {'X-Internal-API-Token': 'invalid'}
    response = client.get('/api/internal/route_info?did=+12345', headers=headers)
    assert response.status_code == 401

def test_route_info_fail_missing_did(client, app):
    """
    GIVEN correct token but missing did parameter
    WHEN GET /api/internal/route_info
    THEN check status 400 Bad Request.
    """
    token = app.config.get('INTERNAL_API_TOKEN')
    headers = {'X-Internal-API-Token': token}
    response = client.get('/api/internal/route_info', headers=headers)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert "Missing 'did' query parameter" in data.get('message', '')