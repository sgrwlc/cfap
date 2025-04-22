# app/services/call_logging_service.py
# -*- coding: utf-8 -*-
"""
Call Logging Service
Handles inserting Call Detail Records (CDRs) from Asterisk
and updating related counters.
Adds/Updates objects in the session but DOES NOT COMMIT.
"""
import logging # Use standard logging
from datetime import datetime
from sqlalchemy.exc import IntegrityError
# from flask import current_app # No longer needed at module level

from app.database.models.call_log import CallLogModel
from app.database.models.campaign import CampaignClientSettingsModel
from app.extensions import db
from app.utils.exceptions import ServiceError, ValidationError, ConflictError, ResourceNotFound


# Use standard Python logger - Flask will configure handlers
log = logging.getLogger(__name__) # Corrected: Use standard logger


class CallLoggingService:

    @staticmethod
    def log_call(cdr_data: dict) -> int:
        """
        Adds a call log record to the session and stages counter updates if applicable.
        DOES NOT COMMIT the transaction.

        Args:
            cdr_data (dict): A dictionary containing call details from Asterisk, validated by schema.

        Returns:
            int: The ID of the newly created CallLogModel record (available after flush).

        Raises:
            ValidationError: If required data is missing (should be caught by schema ideally).
            ConflictError: If the asterisk_uniqueid already exists.
            ResourceNotFound: If the campaign_client_setting_id for counter increment is invalid.
            ServiceError: For database integrity errors or unexpected errors during flush.
        """
        required_fields = ['incoming_did_number', 'timestamp_start', 'call_status', 'asterisk_uniqueid']
        if not all(key in cdr_data for key in required_fields):
            missing = [key for key in required_fields if key not in cdr_data]
            log.error(f"Service Error: Missing required CDR fields: {missing}. Data: {cdr_data}")
            raise ValidationError(f"Internal Error: Missing required CDR fields: {', '.join(missing)}")

        unique_id = cdr_data.get('asterisk_uniqueid')
        final_call_status = cdr_data.get('call_status', 'UNKNOWN').upper()

        log.info(f"Attempting to log call: Asterisk Unique ID: {unique_id}, Status: {final_call_status}")

        increment_counter = False
        ccs_id_to_increment = None
        if final_call_status == 'ANSWERED':
            ccs_id_raw = cdr_data.get('campaign_client_setting_id')
            if ccs_id_raw:
                try:
                    ccs_id_to_increment = int(ccs_id_raw)
                    increment_counter = True
                    log.debug(f"Call {unique_id} (ANSWERED) linked to Setting ID {ccs_id_to_increment}. Will increment counter.")
                except (ValueError, TypeError):
                     log.warning(f"Invalid campaign_client_setting_id format received: '{ccs_id_raw}' for call {unique_id}. Counter will not be incremented.")
                     increment_counter = False
                     ccs_id_to_increment = None
            else:
                 log.debug(f"Call {unique_id} (ANSWERED) but no campaign_client_setting_id provided. Counter will not be incremented.")

        session = db.session
        try:
            # 1. Create Call Log entry
            new_log = CallLogModel(
                user_id=cdr_data.get('user_id'),
                campaign_id=cdr_data.get('campaign_id'),
                did_id=cdr_data.get('did_id'),
                client_id=cdr_data.get('client_id'),
                campaign_client_setting_id=ccs_id_to_increment,
                incoming_did_number=cdr_data['incoming_did_number'],
                caller_id_num=cdr_data.get('caller_id_num'),
                caller_id_name=cdr_data.get('caller_id_name'),
                timestamp_start=cdr_data['timestamp_start'],
                timestamp_answered=cdr_data.get('timestamp_answered'),
                timestamp_end=cdr_data.get('timestamp_end'),
                duration_seconds=cdr_data.get('duration_seconds'),
                billsec_seconds=cdr_data.get('billsec_seconds'),
                call_status=final_call_status,
                hangup_cause_code=cdr_data.get('hangup_cause_code'),
                hangup_cause_text=cdr_data.get('hangup_cause_text'),
                asterisk_uniqueid=unique_id,
                asterisk_linkedid=cdr_data.get('asterisk_linkedid')
            )
            session.add(new_log)
            log.debug(f"Created CallLogModel instance for {unique_id} in session.")

            # 2. Increment Counter (if applicable)
            if increment_counter and ccs_id_to_increment is not None:
                log.debug(f"Staging counter increment for CampaignClientSetting ID: {ccs_id_to_increment}")
                setting_to_update = session.get(CampaignClientSettingsModel, ccs_id_to_increment)
                if not setting_to_update:
                     log.error(f"Counter increment failed: CampaignClientSetting ID {ccs_id_to_increment} not found for call {unique_id}.")
                     raise ResourceNotFound(f"CampaignClientSetting ID {ccs_id_to_increment} not found during counter update.")
                else:
                     setting_to_update.current_total_calls = CampaignClientSettingsModel.current_total_calls + 1
                     log.debug(f"Increment operation staged for setting ID {ccs_id_to_increment}.")

            # Flush the session
            session.flush()
            log_id = new_log.id
            if log_id is None:
                 raise ServiceError("Failed to obtain log ID after flush.")

            log.info(f"Call log {log_id} (Asterisk ID: {unique_id}) staged successfully in session.")
            return log_id

        except IntegrityError as e:
            session.rollback()
            log.warning(f"Database integrity error logging call {unique_id}: {e}", exc_info=True)
            if 'unique constraint' in str(e.orig).lower() and 'call_logs_asterisk_uniqueid_key' in str(e.orig).lower():
                 raise ConflictError(f"Duplicate Asterisk Unique ID: {unique_id}")
            else:
                 raise ServiceError(f"Database integrity error logging call: {e.orig}")
        except Exception as e:
            session.rollback()
            log.exception(f"Unexpected error logging call {unique_id}: {e}")
            if isinstance(e, (ValidationError, ConflictError, ResourceNotFound)): raise e
            raise ServiceError(f"Unexpected error staging call log: {e}")