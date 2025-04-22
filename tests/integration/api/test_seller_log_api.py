# tests/integration/api/test_seller_log_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the Seller Call Log endpoint (/api/seller/logs).
Relies on transactional fixture and service calls (no commits) for setup.
"""
import json
import pytest
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete

# Import Models for DB checks and setup helpers
from app.database.models import UserModel, CampaignModel, DidModel, ClientModel, CallLogModel, CampaignClientSettingsModel
# Import Services for setup
from app.services.user_service import UserService
from app.services.did_service import DidService
from app.services.campaign_service import CampaignService
# from app.services.client_service import ClientService # Clients assumed from sample data
from app.services.call_logging_service import CallLoggingService # To create logs directly
# Import db for direct session usage in fixture if needed
from app.extensions import db

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_client (seller)

# Helper to get seller ID
def get_seller_id(session):
    user = session.query(UserModel).filter_by(username="pytest_seller").one_or_none()
    assert user is not None, "Test setup failed: pytest_seller not found."
    return user.id

# Helper function to create test log entries data dictionary (same as before)
def create_test_log_data(user_id, campaign_id, did_id, client_id, ccs_id, status, start_time_offset_days=0):
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=start_time_offset_days)
    ts_part = start_time.strftime('%Y%m%d%H%M%S%f')
    unique_part = f"{user_id}-{campaign_id or 'N'}-{did_id or 'N'}-{client_id or 'N'}-{ts_part}"
    return {
        'user_id': user_id, 'campaign_id': campaign_id, 'did_id': did_id, 'client_id': client_id,
        'campaign_client_setting_id': ccs_id,
        'incoming_did_number': f"+1555{did_id or '000'}{campaign_id or '000'}{client_id or '000'}",
        'caller_id_num': f"+1999{start_time_offset_days}000",
        'timestamp_start': start_time,
        'timestamp_answered': start_time + timedelta(seconds=5) if status == "ANSWERED" else None,
        'timestamp_end': start_time + timedelta(seconds=65) if status != "REJECTED_CC" else start_time + timedelta(seconds=1),
        'duration_seconds': 60 if status == "ANSWERED" else (65 if status != "REJECTED_CC" else 1),
        'billsec_seconds': 60 if status == "ANSWERED" else 0,
        'call_status': status,
        'asterisk_uniqueid': f"test-uid-{unique_part}",
        'asterisk_linkedid': f"test-lid-{unique_part}",
    }

# Helper function to create log object using service (relies on caller transaction)
def create_log_object(session, log_data):
     """Calls logging service (no commit) and returns the persisted ORM object."""
     log_id = CallLoggingService.log_call(log_data) # Adds to session, flushes
     assert log_id is not None, "CallLoggingService failed to return ID"
     # Flush should happen in service, but double check here if needed
     # session.flush()
     log_obj = session.get(CallLogModel, log_id)
     assert log_obj is not None, f"Failed to fetch newly created log with ID {log_id}"
     return log_obj


# --- Test Setup Data Fixture ---
@pytest.fixture(scope="function")
def seller_log_setup(session, logged_in_client): # Depends on session and login
    """
    Fixture to set up common data for seller log tests within a transaction.
    Uses service layer calls (no commits) and relies on the 'session' fixture for rollback.
    """
    log.info("Setting up seller_log_setup fixture...")
    seller_id = get_seller_id(session)
    returned_data = {"seller_id": seller_id}

    try:
        # Create DIDs (using service, no commit)
        did1 = DidService.add_did(seller_id, "+15559991001", "Log Test DID 1 API")
        did2 = DidService.add_did(seller_id, "+15559991002", "Log Test DID 2 API")

        # Create Campaigns (using service, no commit)
        camp1 = CampaignService.create_campaign(seller_id, "Log Test Camp 1 API", "priority", 30)
        camp2 = CampaignService.create_campaign(seller_id, "Log Test Camp 2 API", "round_robin", 25)

        # Get Clients (assume they exist from sample data loaded by 'db' fixture)
        client1 = session.get(ClientModel, 1)
        client2 = session.get(ClientModel, 2)
        if not client1 or not client2: pytest.fail("Sample clients 1 or 2 not found.")

        # Link clients to campaigns (using service, no commit)
        setting1_1 = CampaignService.add_client_to_campaign(camp1.id, seller_id, client1.id, {"max_concurrency": 1, "forwarding_priority": 0, "weight": 100})
        setting1_2 = CampaignService.add_client_to_campaign(camp1.id, seller_id, client2.id, {"max_concurrency": 1, "forwarding_priority": 1, "weight": 100})
        setting2_2 = CampaignService.add_client_to_campaign(camp2.id, seller_id, client2.id, {"max_concurrency": 1, "forwarding_priority": 0, "weight": 100})

        # Flush to ensure all IDs are generated before creating logs
        session.flush()
        returned_data.update({
            "did1_id": did1.id, "did2_id": did2.id, "camp1_id": camp1.id, "camp2_id": camp2.id,
            "client1_id": client1.id, "client2_id": client2.id,
            "setting1_1_id": setting1_1.id, "setting1_2_id": setting1_2.id, "setting2_2_id": setting2_2.id
        })

        # Create log entries using helper (calls service, no commit)
        log_data1 = create_test_log_data(seller_id, camp1.id, did1.id, client1.id, setting1_1.id, "ANSWERED", 0)
        log1 = create_log_object(session, log_data1)

        log_data2 = create_test_log_data(seller_id, camp1.id, did1.id, client2.id, setting1_2.id, "NOANSWER", 1)
        log2 = create_log_object(session, log_data2)

        log_data3 = create_test_log_data(seller_id, camp2.id, did2.id, client2.id, setting2_2.id, "BUSY", 1)
        log3 = create_log_object(session, log_data3)

        log_data4 = create_test_log_data(seller_id, camp1.id, did1.id, None, None, "REJECTED_CC", 2)
        log4 = create_log_object(session, log_data4)

        # Final flush of log data within the transaction
        session.flush()
        returned_data.update({"log1_id": log1.id, "log2_id": log2.id, "log3_id": log3.id, "log4_id": log4.id})
        log.info("seller_log_setup fixture setup complete.")

        # NO COMMIT HERE - relies on session fixture rollback

        yield returned_data

    except Exception as e:
         log.error(f"Error during seller_log_setup: {e}", exc_info=True)
         pytest.fail(f"Failed during seller_log_setup: {e}")


# --- Test GET /api/seller/logs ---

def test_seller_get_logs_success_paginated(logged_in_client, seller_log_setup):
    """ GIVEN seller has logs; WHEN GET /logs with pagination; THEN 200 """
    # Arrange: seller_log_setup created 4 logs

    # Act: Get page 1, 2 items per page
    response = logged_in_client.get('/api/seller/logs?page=1&per_page=2')

    # Assert
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('page') == 1 and data.get('perPage') == 2
    # Total should reflect logs created IN THIS TEST SCOPE by the fixture
    assert data.get('total') == 4 and data.get('pages') == 2 and len(data['items']) == 2
    assert data['items'][0]['id'] == seller_log_setup['log1_id'] # Most recent
    second_log_id = data['items'][1]['id']
    assert second_log_id in [seller_log_setup['log2_id'], seller_log_setup['log3_id']] # Yesterday's logs


def test_seller_get_logs_filter_campaign(logged_in_client, seller_log_setup):
    """ GIVEN seller has logs; WHEN GET /logs filtered by campaign_id; THEN 200 """
    camp1_id = seller_log_setup['camp1_id']
    response = logged_in_client.get(f'/api/seller/logs?campaign_id={camp1_id}')

    assert response.status_code == 200
    data = response.get_json()
    assert data.get('total') == 3 # log1, log2, log4 are camp1
    assert all(item['campaign']['id'] == camp1_id for item in data['items'])


def test_seller_get_logs_filter_did(logged_in_client, seller_log_setup):
    """ GIVEN seller has logs; WHEN GET /logs filtered by did_id; THEN 200 """
    did1_id = seller_log_setup['did1_id']
    response = logged_in_client.get(f'/api/seller/logs?did_id={did1_id}')

    assert response.status_code == 200
    data = response.get_json()
    assert data.get('total') == 3 # log1, log2, log4 used did1
    assert all(item['did']['id'] == did1_id for item in data['items'])


def test_seller_get_logs_filter_client(logged_in_client, seller_log_setup):
    """ GIVEN seller has logs; WHEN GET /logs filtered by client_id; THEN 200 """
    client2_id = seller_log_setup['client2_id']
    response = logged_in_client.get(f'/api/seller/logs?client_id={client2_id}')

    assert response.status_code == 200
    data = response.get_json()
    assert data.get('total') == 2 # log2, log3 involved client2
    assert all(item['client']['id'] == client2_id for item in data['items'])


def test_seller_get_logs_filter_status(logged_in_client, seller_log_setup):
    """ GIVEN seller has logs; WHEN GET /logs filtered by call_status; THEN 200 """
    response = logged_in_client.get(f'/api/seller/logs?call_status=ANSWERED')

    assert response.status_code == 200
    data = response.get_json()
    assert data.get('total') == 1 # Only log1 was ANSWERED
    assert data['items'][0]['id'] == seller_log_setup['log1_id']


def test_seller_get_logs_filter_date(logged_in_client, seller_log_setup):
    """ GIVEN seller has logs; WHEN GET /logs filtered by date range; THEN 200 """
    yesterday_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')

    response = logged_in_client.get(f'/api/seller/logs?start_date={yesterday_str}&end_date={yesterday_str}')

    assert response.status_code == 200
    data = response.get_json()
    assert data.get('total') == 2 # log2, log3 were yesterday
    log_ids = {item['id'] for item in data['items']}
    assert seller_log_setup['log2_id'] in log_ids and seller_log_setup['log3_id'] in log_ids


def test_seller_get_logs_filter_invalid_date(logged_in_client):
    """ WHEN GET /logs with invalid date format; THEN 400 """
    response = logged_in_client.get('/api/seller/logs?start_date=2023/01/01')
    assert response.status_code == 400
    assert "Invalid start_date format" in response.get_json().get('message', '')


def test_seller_get_logs_filter_campaign_not_owned(logged_in_client, session):
    """ WHEN GET /logs filtered by campaign_id not owned by seller; THEN 400 """
    # Arrange: Create campaign for another user (use service, will rollback)
    other_user = UserService.create_user("otherseller_log_api", "other_log_api@s.com", "Pass123")
    session.flush()
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Log Camp API", "priority", 30)
    session.flush()
    other_campaign_id = other_campaign.id

    # Act
    response = logged_in_client.get(f'/api/seller/logs?campaign_id={other_campaign_id}')

    # Assert: Route now relies on main query, which won't find logs for this campaign for this user.
    # It should return 200 OK with an empty list, not 400.
    assert response.status_code == 200
    data = response.get_json()
    assert data.get('total') == 0
    assert len(data.get('items', [])) == 0


def test_seller_get_logs_unauthorized(client):
    """ GIVEN no user logged in; WHEN GET /logs; THEN 401 """
    response = client.get('/api/seller/logs')
    assert response.status_code == 401
