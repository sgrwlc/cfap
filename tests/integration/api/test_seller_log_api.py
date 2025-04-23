# tests/integration/api/test_seller_log_api.py
# -*- coding: utf-8 -*-
"""
Integration tests for the Seller Call Log endpoint (/api/seller/logs),
aligned with refactored services and routes (Phase 5 Final).
"""
import json
import pytest
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete # Keep for potential direct cleanup if needed

# Import Models for DB checks and setup helpers
from app.database.models import (
    UserModel, CampaignModel, DidModel, ClientModel, CallLogModel, CampaignClientSettingsModel
)
# Import Services for setup within session fixture
from app.services.user_service import UserService
from app.services.did_service import DidService
from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService
from app.services.call_logging_service import CallLoggingService
# Import db for direct session usage in fixture if needed
from app.extensions import db

log = logging.getLogger(__name__)

# Fixtures: client, session, db, logged_in_client (seller), logged_in_admin_client

# Helper to get seller ID
def get_seller_id(session):
    user = session.query(UserModel).filter_by(username="pytest_seller").one()
    return user.id

# Helper function to create test log entries data dictionary (Unchanged)
def create_test_log_data(user_id, campaign_id, did_id, client_id, ccs_id, status, start_time_offset_days=0):
    """Creates a dictionary of log data for CallLoggingService."""
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=start_time_offset_days)
    ts_part = start_time.strftime('%Y%m%d%H%M%S%f')
    unique_part = f"{user_id}-{campaign_id or 'N'}-{did_id or 'N'}-{client_id or 'N'}-{ts_part}"
    return {
        'user_id': user_id, 'campaign_id': campaign_id, 'did_id': did_id,
        'client_id': client_id, 'campaign_client_setting_id': ccs_id,
        'incoming_did_number': f"+1555{did_id or '000'}{campaign_id or '000'}{client_id or '000'}",
        'caller_id_num': f"+1999{start_time_offset_days}000",
        'timestamp_start': start_time,
        'timestamp_answered': start_time + timedelta(seconds=5) if status == "ANSWERED" else None,
        'timestamp_end': start_time + timedelta(seconds=65) if status != "REJECTED_CC" else start_time + timedelta(seconds=1),
        'duration_seconds': 60 if status == "ANSWERED" else (65 if status != "REJECTED_CC" else 1),
        'billsec_seconds': 60 if status == "ANSWERED" else 0,
        'call_status': status,
        'asterisk_uniqueid': f"test-uid-p5-{unique_part}",
        'asterisk_linkedid': f"test-lid-p5-{unique_part}",
    }

# Helper function to create log using service (relies on caller transaction/flush)
def stage_log_object(session, log_data):
     """Calls logging service (no commit) and flushes session to get ID."""
     log_id = CallLoggingService.log_call(log_data) # Service stages log and counter update
     session.flush() # Flush the transaction to get the ID
     assert log_id is not None, f"CallLoggingService did not return an ID for uniqueid {log_data.get('asterisk_uniqueid')}"
     log_obj = session.get(CallLogModel, log_id) # Fetch the object after flush
     assert log_obj is not None, f"Failed to fetch staged log with ID {log_id}"
     log.debug(f"Setup: Staged Log ID {log_id} (Status: {log_data['call_status']})")
     return log_obj


# --- Test Setup Data Fixture ---
@pytest.fixture(scope="function")
def seller_log_setup(session, logged_in_client): # Depends on session and login fixtures
    """
    Fixture to set up test data for seller log tests within a transaction.
    Creates campaigns, DIDs, links, and logs using service calls (no commit).
    Relies on the main 'session' fixture for rollback.
    """
    log.info("Setting up seller_log_setup fixture data...")
    seller_id = get_seller_id(session)
    returned_data = {"seller_id": seller_id}

    try:
        # --- Create Test Data using Service Layer calls ---
        # DIDs
        did1 = DidService.add_did(seller_id, "+15559991001_p5", "Log Test DID 1 P5")
        did2 = DidService.add_did(seller_id, "+15559991002_p5", "Log Test DID 2 P5")
        session.flush()
        returned_data.update({"did1_id": did1.id, "did2_id": did2.id})

        # Campaigns
        camp1 = CampaignService.create_campaign(seller_id, "Log Test Camp 1 P5", "priority", 30)
        camp2 = CampaignService.create_campaign(seller_id, "Log Test Camp 2 P5", "round_robin", 25)
        session.flush()
        returned_data.update({"camp1_id": camp1.id, "camp2_id": camp2.id})

        # Get Clients (from sample data loaded by 'db' fixture)
        client1 = session.get(ClientModel, 1)
        client2 = session.get(ClientModel, 2)
        assert client1 and client2, "Sample clients 1 or 2 not found."
        returned_data.update({"client1_id": client1.id, "client2_id": client2.id})

        # Link clients to campaigns
        setting1_1 = CampaignService.add_client_to_campaign(camp1.id, seller_id, client1.id, {"max_concurrency": 1, "forwarding_priority": 0, "weight": 100})
        setting1_2 = CampaignService.add_client_to_campaign(camp1.id, seller_id, client2.id, {"max_concurrency": 1, "forwarding_priority": 1, "weight": 100})
        setting2_2 = CampaignService.add_client_to_campaign(camp2.id, seller_id, client2.id, {"max_concurrency": 1, "forwarding_priority": 0, "weight": 100})
        session.flush()
        returned_data.update({
            "setting1_1_id": setting1_1.id, "setting1_2_id": setting1_2.id, "setting2_2_id": setting2_2.id
        })

        # Create log entries using helper (stages log + counter increment, flushes session)
        log1_data = create_test_log_data(seller_id, camp1.id, did1.id, client1.id, setting1_1.id, "ANSWERED", 0) # Today
        log1 = stage_log_object(session, log1_data)

        log2_data = create_test_log_data(seller_id, camp1.id, did1.id, client2.id, setting1_2.id, "NOANSWER", 1) # Yesterday
        log2 = stage_log_object(session, log2_data)

        log3_data = create_test_log_data(seller_id, camp2.id, did2.id, client2.id, setting2_2.id, "BUSY", 1)     # Yesterday
        log3 = stage_log_object(session, log3_data)

        log4_data = create_test_log_data(seller_id, camp1.id, did1.id, None, None, "REJECTED_CC", 2) # 2 days ago, rejected
        log4 = stage_log_object(session, log4_data)

        # NO COMMIT HERE - session fixture handles rollback

        returned_data.update({"log1_id": log1.id, "log2_id": log2.id, "log3_id": log3.id, "log4_id": log4.id})
        log.info("Finished seller_log_setup fixture setup.")
        yield returned_data

    except Exception as e:
         log.exception(f"Error during seller_log_setup: {e}")
         pytest.fail(f"Failed during seller_log_setup: {e}")


# --- Test GET /api/seller/logs ---

def test_seller_get_logs_success_paginated(logged_in_client, seller_log_setup):
    """
    GIVEN seller logged in and has logs (via setup fixture)
    WHEN GET /api/seller/logs with pagination
    THEN check status 200 OK and correct page of own logs returned.
    """
    # Arrange: seller_log_setup created 4 logs

    # Act: Get page 1, 2 items per page
    response = logged_in_client.get('/api/seller/logs?page=1&per_page=2')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('page') == 1
    assert data.get('perPage') == 2
    assert data.get('total') == 4 # Correct total based on setup fixture
    assert data.get('pages') == 2
    assert len(data['items']) == 2
    # Check the most recent log is first
    assert data['items'][0]['id'] == seller_log_setup['log1_id']
    # Check the second item (log2/log3 are tied for timestamp)
    assert data['items'][1]['id'] in [seller_log_setup['log2_id'], seller_log_setup['log3_id']]


def test_seller_get_logs_filter_campaign(logged_in_client, seller_log_setup):
    """
    GIVEN seller logged in and has logs for multiple campaigns
    WHEN GET /api/seller/logs filtered by campaign_id
    THEN check status 200 OK and only logs for that campaign are returned.
    """
    camp1_id = seller_log_setup['camp1_id']
    response = logged_in_client.get(f'/api/seller/logs?campaign_id={camp1_id}')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 3 # log1, log2, log4 belong to camp1
    assert len(data['items']) == 3
    assert all(item['campaign']['id'] == camp1_id for item in data['items'])


def test_seller_get_logs_filter_did(logged_in_client, seller_log_setup):
    """
    GIVEN seller logged in and has logs for multiple DIDs
    WHEN GET /api/seller/logs filtered by did_id
    THEN check status 200 OK and only logs for that DID are returned.
    """
    did1_id = seller_log_setup['did1_id']
    response = logged_in_client.get(f'/api/seller/logs?did_id={did1_id}')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 3 # log1, log2, log4 used did1
    assert len(data['items']) == 3
    assert all(item['did']['id'] == did1_id for item in data['items'])


def test_seller_get_logs_filter_client(logged_in_client, seller_log_setup):
    """
    GIVEN seller logged in and has logs involving multiple clients
    WHEN GET /api/seller/logs filtered by client_id
    THEN check status 200 OK and only logs involving that client are returned.
    """
    client2_id = seller_log_setup['client2_id']
    response = logged_in_client.get(f'/api/seller/logs?client_id={client2_id}')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 2 # log2, log3 involved client2
    assert len(data['items']) == 2
    assert all(item['client']['id'] == client2_id for item in data['items'])


def test_seller_get_logs_filter_status(logged_in_client, seller_log_setup):
    """
    GIVEN seller logged in and has logs with different statuses
    WHEN GET /api/seller/logs filtered by call_status
    THEN check status 200 OK and only logs with that status are returned.
    """
    response = logged_in_client.get('/api/seller/logs?call_status=ANSWERED')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 1 # Only log1 was ANSWERED
    assert len(data['items']) == 1
    assert data['items'][0]['id'] == seller_log_setup['log1_id']


def test_seller_get_logs_filter_date(logged_in_client, seller_log_setup):
    """
    GIVEN seller logged in and has logs on different dates
    WHEN GET /api/seller/logs filtered by date range
    THEN check status 200 OK and only logs within that range are returned.
    """
    # Arrange: Get dates relative to today
    yesterday_dt = datetime.now(timezone.utc) - timedelta(days=1)
    yesterday_str = yesterday_dt.strftime('%Y-%m-%d')

    # Act: Get logs from yesterday only
    response = logged_in_client.get(f'/api/seller/logs?start_date={yesterday_str}&end_date={yesterday_str}')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 2 # log2, log3 were yesterday
    assert len(data['items']) == 2
    log_ids = {item['id'] for item in data['items']}
    assert seller_log_setup['log2_id'] in log_ids
    assert seller_log_setup['log3_id'] in log_ids


def test_seller_get_logs_filter_invalid_date(logged_in_client):
    """
    GIVEN seller logged in
    WHEN GET /api/seller/logs with invalid date format
    THEN check status 400 Bad Request.
    """
    response = logged_in_client.get('/api/seller/logs?start_date=2023/01/01') # Invalid format
    assert response.status_code == 400
    data = json.loads(response.data)
    assert "Invalid start_date format" in data.get('message', '')


def test_seller_get_logs_filter_campaign_not_owned(logged_in_client, session):
    """
    GIVEN seller logged in
    WHEN GET /api/seller/logs filtered by campaign_id not owned by seller
    THEN check status 200 OK and return empty list (as no logs for this user match).
    """
    # Arrange: Create campaign for another user
    other_user = UserService.create_user("otherseller_log_p5", "other_log_p5@s.com", "Pass123")
    session.flush()
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Log Camp P5", "priority", 30)
    session.flush()
    other_campaign_id = other_campaign.id

    # Act: Filter by other user's campaign ID
    response = logged_in_client.get(f'/api/seller/logs?campaign_id={other_campaign_id}')

    # Assert: Route filtering logic correctly finds no logs for the current user matching this campaign
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 0
    assert len(data['items']) == 0


def test_seller_get_logs_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/seller/logs requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/seller/logs')
    assert response.status_code == 401