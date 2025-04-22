# -*- coding: utf-8 -*-
"""
Integration tests for the Seller Call Log endpoint (/api/seller/logs).
"""
import json
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete # Import delete for fixture cleanup

# Import Models for DB checks and setup helpers
from app.database.models import UserModel, CampaignModel, DidModel, ClientModel, CallLogModel, CampaignClientSettingsModel
# Import Services for setup
from app.services.user_service import UserService
from app.services.did_service import DidService
from app.services.campaign_service import CampaignService
from app.services.client_service import ClientService # To ensure clients exist
from app.services.call_logging_service import CallLoggingService # To create logs directly
# Import db for direct session usage in fixture if needed
from app.extensions import db

# Fixtures: client, session, db, logged_in_client (seller), logged_in_admin_client

# Helper to get seller ID
def get_seller_id(session):
    user = session.query(UserModel).filter_by(username="pytest_seller").one_or_none()
    # If user doesn't exist yet (fixture might create it) - re-query after potential creation
    if user is None:
         user = session.query(UserModel).filter_by(username="pytest_seller").one_or_none()
    assert user is not None, "Test setup failed: pytest_seller not found. Check logged_in_client fixture setup."
    return user.id

# Helper function to create test log entries data dictionary
def create_test_log_data(user_id, campaign_id, did_id, client_id, ccs_id, status, start_time_offset_days=0):
    """Creates a dictionary of log data for CallLoggingService."""
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=start_time_offset_days)
    # Generate reasonably unique IDs for testing, real app uses Asterisk values
    # Use timestamp with microseconds for higher uniqueness chance
    ts_part = start_time.strftime('%Y%m%d%H%M%S%f')
    unique_part = f"{user_id}-{campaign_id or 'N'}-{did_id or 'N'}-{client_id or 'N'}-{ts_part}"
    return {
        'user_id': user_id,
        'campaign_id': campaign_id,
        'did_id': did_id,
        'client_id': client_id,
        'campaign_client_setting_id': ccs_id,
        'incoming_did_number': f"+1555{did_id or '000'}{campaign_id or '000'}{client_id or '000'}", # Example DID number
        'caller_id_num': f"+1999{start_time_offset_days}000",
        'timestamp_start': start_time,
        'timestamp_answered': start_time + timedelta(seconds=5) if status == "ANSWERED" else None,
        'timestamp_end': start_time + timedelta(seconds=65) if status != "REJECTED_CC" else start_time + timedelta(seconds=1), # Adjust REJECTED status used
        'duration_seconds': 60 if status == "ANSWERED" else (65 if status != "REJECTED_CC" else 1),
        'billsec_seconds': 60 if status == "ANSWERED" else 0,
        'call_status': status,
        'asterisk_uniqueid': f"test-uid-{unique_part}",
        'asterisk_linkedid': f"test-lid-{unique_part}",
    }

# Helper function to create log object using service (relies on caller transaction)
def create_log_object(session, log_data):
     """Calls logging service and returns the persisted ORM object."""
     log_id = CallLoggingService.log_call(log_data)
     assert log_id is not None, "CallLoggingService failed to return ID"
     session.flush() # Ensure ID is available if service doesn't flush
     log_obj = session.get(CallLogModel, log_id)
     assert log_obj is not None, f"Failed to fetch newly created log with ID {log_id}"
     return log_obj

# --- Test Setup Data Fixture with Cleanup ---
# tests/integration/api/test_seller_log_api.py

@pytest.fixture(scope="function")
def seller_log_setup(session, logged_in_client): # Depends on session and login
    """
    Fixture to set up common data for seller log tests within a transaction.
    Relies on the main 'session' fixture for rollback.
    """
    print("\nDEBUG: Running seller_log_setup fixture setup...")
    seller_id = get_seller_id(session)
    # Dictionary to return IDs for use in tests
    returned_data = {"seller_id": seller_id}

    try:
        # --- Create Test Data within the session ---
        # Use consistent, predictable names/numbers for easier debugging if needed

        # Create DIDs
        did1 = DidService.add_did(seller_id, "+15559991001", "Log Test DID 1")
        did2 = DidService.add_did(seller_id, "+15559991002", "Log Test DID 2")
        returned_data.update({"did1_id": did1.id, "did2_id": did2.id})

        # Create Campaigns
        camp1 = CampaignService.create_campaign(seller_id, "Log Test Camp 1", "priority", 30)
        camp2 = CampaignService.create_campaign(seller_id, "Log Test Camp 2", "round_robin", 25)
        returned_data.update({"camp1_id": camp1.id, "camp2_id": camp2.id})

        # Get Clients (ensure they exist from sample data fixture 'db')
        client1 = session.get(ClientModel, 1)
        client2 = session.get(ClientModel, 2)
        if not client1 or not client2: pytest.fail("Sample clients 1 or 2 not found. Ensure db fixture loads sample data.")
        returned_data.update({"client1_id": client1.id, "client2_id": client2.id})

        # Link clients to campaigns (add_client_to_campaign should NOT commit)
        setting1_1 = CampaignService.add_client_to_campaign(camp1.id, seller_id, client1.id, {"max_concurrency": 1, "forwarding_priority": 0, "weight": 100})
        setting1_2 = CampaignService.add_client_to_campaign(camp1.id, seller_id, client2.id, {"max_concurrency": 1, "forwarding_priority": 1, "weight": 100})
        setting2_2 = CampaignService.add_client_to_campaign(camp2.id, seller_id, client2.id, {"max_concurrency": 1, "forwarding_priority": 0, "weight": 100})

        # Flush required only if subsequent operations in THIS fixture need the IDs
        session.flush()
        returned_data.update({
            "setting1_1_id": setting1_1.id, "setting1_2_id": setting1_2.id, "setting2_2_id": setting2_2.id
        })
        print(f"DEBUG: Setup - DID1:{did1.id}, DID2:{did2.id}, Camp1:{camp1.id}, Camp2:{camp2.id}")
        print(f"DEBUG: Setup - Sett1_1:{setting1_1.id}, Sett1_2:{setting1_2.id}, Sett2_2:{setting2_2.id}")


        # Create log entries using helper (log_call service should also NOT commit)
        # Helper returns the ORM object after fetching by ID returned from service
        log_data1 = create_test_log_data(seller_id, camp1.id, did1.id, client1.id, setting1_1.id, "ANSWERED", 0) # Today
        log1 = create_log_object(session, log_data1)

        log_data2 = create_test_log_data(seller_id, camp1.id, did1.id, client2.id, setting1_2.id, "NOANSWER", 1) # Yesterday
        log2 = create_log_object(session, log_data2)

        log_data3 = create_test_log_data(seller_id, camp2.id, did2.id, client2.id, setting2_2.id, "BUSY", 1)     # Yesterday
        log3 = create_log_object(session, log_data3)

        log_data4 = create_test_log_data(seller_id, camp1.id, did1.id, None, None, "REJECTED_CC", 2) # 2 days ago, rejected
        log4 = create_log_object(session, log_data4)

        session.flush() # Final flush of setup data within the transaction

        returned_data.update({
            "log1_id": log1.id, "log2_id": log2.id, "log3_id": log3.id, "log4_id": log4.id
        })
        print(f"DEBUG: Setup - Log1:{log1.id}, Log2:{log2.id}, Log3:{log3.id}, Log4:{log4.id}")

        # Yield the dictionary of IDs for tests to use
        yield returned_data

    except Exception as e:
         # If setup fails, rollback immediately and fail the test
         print(f"\nERROR during seller_log_setup: {e}")
         try:
             session.rollback()
         except Exception as rb_err:
             print(f"ERROR during rollback after setup failure: {rb_err}")
         pytest.fail(f"Failed during seller_log_setup: {e}")

    # No 'finally' block needed here - the 'session' fixture handles rollback
    print("\nDEBUG: Exiting seller_log_setup fixture setup.")


# --- Test GET /api/seller/logs ---

def test_seller_get_logs_success_paginated(logged_in_client, seller_log_setup):
    """
    GIVEN seller logged in and has logs
    WHEN GET /api/seller/logs with pagination
    THEN check status 200 OK and correct page of own logs is returned.
    """
    # Arrange: seller_log_setup created 4 logs for the logged-in user

    # Act: Get page 1, 2 items per page
    response = logged_in_client.get('/api/seller/logs?page=1&per_page=2')

    # Assert
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('page') == 1
    assert data.get('perPage') == 2
    # Total should reflect only the logs created within this test's transaction scope by the fixture
    assert data.get('total') == 4
    assert data.get('pages') == 2
    assert len(data['items']) == 2

    # Check the most recent log is first
    assert data['items'][0]['id'] == seller_log_setup['log1_id']

    # Check the second item is EITHER log2 or log3 (since they were created with the same offset)
    second_log_id = data['items'][1]['id']
    assert second_log_id in [seller_log_setup['log2_id'], seller_log_setup['log3_id']]

    # Check basic structure
    assert 'campaign' in data['items'][0] and data['items'][0]['campaign']['id'] == seller_log_setup['camp1_id']
    assert 'did' in data['items'][0] and data['items'][0]['did']['id'] == seller_log_setup['did1_id']
    assert 'client' in data['items'][0] and data['items'][0]['client']['id'] == seller_log_setup['client1_id']

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
    response = logged_in_client.get(f'/api/seller/logs?call_status=ANSWERED')

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data.get('total') == 1 # Only log1 was ANSWERED
    assert len(data['items']) == 1
    assert data['items'][0]['id'] == seller_log_setup['log1_id']
    assert data['items'][0]['callStatus'] == 'ANSWERED'


def test_seller_get_logs_filter_date(logged_in_client, seller_log_setup):
    """
    GIVEN seller logged in and has logs on different dates
    WHEN GET /api/seller/logs filtered by date range
    THEN check status 200 OK and only logs within that range are returned.
    """
    # Arrange: Get dates relative to today
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
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
    response = logged_in_client.get('/api/seller/logs?start_date=2023/01/01')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert "Invalid date format" in data.get('message', '')


def test_seller_get_logs_filter_campaign_not_owned(logged_in_client, session):
    """
    GIVEN seller logged in
    WHEN GET /api/seller/logs filtered by campaign_id not owned by seller
    THEN check status 400 Bad Request.
    """
    # Arrange: Create campaign for another user
    other_user = UserService.create_user("otherseller_log", "other_log@s.com", "Pass123")
    other_campaign = CampaignService.create_campaign(other_user.id, "Other Log Camp", "priority", 30)
    # No commit needed here, service doesn't commit, session fixture rolls back

    session.flush() # Flush to get ID
    other_campaign_id = other_campaign.id

    # Act
    response = logged_in_client.get(f'/api/seller/logs?campaign_id={other_campaign_id}')

    # Assert
    assert response.status_code == 400
    data = json.loads(response.data)
    assert f"Campaign ID {other_campaign_id} not found or not owned by user" in data.get('message', '')


def test_seller_get_logs_unauthorized(client):
    """
    GIVEN no user logged in
    WHEN GET /api/seller/logs is requested
    THEN check status 401 Unauthorized.
    """
    response = client.get('/api/seller/logs')
    assert response.status_code == 401