# -*- coding: utf-8 -*-
"""
Call Logging Service
Handles inserting Call Detail Records (CDRs) from Asterisk
and updating related counters.
"""
import logging
from datetime import datetime
from sqlalchemy.exc import IntegrityError

from app.database.models.call_log import CallLogModel
from app.database.models.campaign import CampaignClientSettingsModel
from app.extensions import db

# Configure logging for this service
logger = logging.getLogger(__name__)

class CallLoggingService:

    @staticmethod
    def log_call(cdr_data: dict) -> int | None:
        """
        Logs a call record received from Asterisk and updates counters if applicable.

        Args:
            cdr_data (dict): A dictionary containing call details from Asterisk.
                             Expected keys (example): user_id, campaign_id, did_id,
                             client_id (optional), campaign_client_setting_id (optional),
                             incoming_did_number, caller_id_num, caller_id_name,
                             timestamp_start, timestamp_answered, timestamp_end,
                             duration_seconds, billsec_seconds, call_status,
                             hangup_cause_code, hangup_cause_text,
                             asterisk_uniqueid, asterisk_linkedid

        Returns:
            int or None: The ID of the created CallLogModel record, or None if failed.

        Raises:
            ValueError: If required data is missing or invalid, or if update fails.
            # Consider ServiceError
        """
        # Basic validation for absolutely required fields
        required_fields = ['incoming_did_number', 'timestamp_start', 'call_status', 'asterisk_uniqueid']
        if not all(key in cdr_data for key in required_fields):
            missing = [key for key in required_fields if key not in cdr_data]
            logger.error(f"Missing required CDR fields: {missing}. Data: {cdr_data}")
            raise ValueError(f"Missing required CDR fields: {', '.join(missing)}")

        unique_id = cdr_data.get('asterisk_uniqueid')
        logger.info(f"Logging call request received for Asterisk Unique ID: {unique_id}, Status: {cdr_data.get('call_status')}")

        # Determine if the call counts towards total caps
        # Rule: Count if status is 'ANSWERED' and campaign_client_setting_id is provided
        # (Could add billsec > min_duration check here if needed)
        increment_counter = False
        ccs_id_to_increment = None
        final_call_status = cdr_data.get('call_status', 'UNKNOWN').upper() # Normalize status

        if final_call_status == 'ANSWERED':
            ccs_id_raw = cdr_data.get('campaign_client_setting_id')
            if ccs_id_raw:
                try:
                    ccs_id_to_increment = int(ccs_id_raw)
                    increment_counter = True
                    logger.debug(f"Call {unique_id} is ANSWERED and linked to Setting ID {ccs_id_to_increment}. Will increment counter.")
                except (ValueError, TypeError):
                     logger.warning(f"Invalid campaign_client_setting_id format received: '{ccs_id_raw}' for call {unique_id}. Counter will not be incremented.")
            else:
                 logger.debug(f"Call {unique_id} is ANSWERED but no campaign_client_setting_id provided. Counter will not be incremented.")


        session = db.session
        try:
            # 1. Create Call Log entry
            new_log = CallLogModel(
                user_id=cdr_data.get('user_id'), # Can be null if user deleted later
                campaign_id=cdr_data.get('campaign_id'), # Can be null
                did_id=cdr_data.get('did_id'), # Can be null
                client_id=cdr_data.get('client_id'), # Can be null
                campaign_client_setting_id=ccs_id_to_increment, # Store the ID if call was answered and linked

                incoming_did_number=cdr_data['incoming_did_number'],
                caller_id_num=cdr_data.get('caller_id_num'),
                caller_id_name=cdr_data.get('caller_id_name'),

                # Ensure timestamps are valid datetime objects or None
                timestamp_start=cdr_data.get('timestamp_start'), # AGI should provide valid ISO format or similar
                timestamp_answered=cdr_data.get('timestamp_answered'),
                timestamp_end=cdr_data.get('timestamp_end'),

                duration_seconds=cdr_data.get('duration_seconds'),
                billsec_seconds=cdr_data.get('billsec_seconds'),

                call_status=final_call_status, # Use normalized status
                hangup_cause_code=cdr_data.get('hangup_cause_code'),
                hangup_cause_text=cdr_data.get('hangup_cause_text'),

                asterisk_uniqueid=unique_id,
                asterisk_linkedid=cdr_data.get('asterisk_linkedid')
            )
            session.add(new_log)
            logger.debug(f"Created CallLogModel instance for {unique_id}.")

            # 2. Increment Counter (if applicable) - Atomic Update
            if increment_counter and ccs_id_to_increment is not None:
                logger.debug(f"Attempting to increment current_total_calls for CampaignClientSetting ID: {ccs_id_to_increment}")
                result = session.query(CampaignClientSettingsModel)\
                    .filter(CampaignClientSettingsModel.id == ccs_id_to_increment)\
                    .update(
                        {'current_total_calls': CampaignClientSettingsModel.current_total_calls + 1},
                        synchronize_session=False # Important for efficiency with bulk operations or when not needing immediate ORM update
                    )
                if result == 0:
                     # This means the setting ID didn't exist, which is problematic
                     logger.error(f"Failed to increment counter: CampaignClientSetting ID {ccs_id_to_increment} not found for call {unique_id}.")
                     # Decide whether to rollback the log insertion or just log the error
                     # For now, we'll proceed with logging the error but commit the log record
                     # raise ValueError(f"CampaignClientSetting ID {ccs_id_to_increment} not found during counter update.")
                else:
                     logger.info(f"Successfully incremented current_total_calls for CampaignClientSetting ID: {ccs_id_to_increment}")


            # Commit transaction
            session.commit()
            logger.info(f"Successfully logged call {unique_id} with DB ID {new_log.id}")
            return new_log.id

        except IntegrityError as e:
            session.rollback()
            # Log error e
            if 'unique constraint' in str(e.orig).lower() and 'call_logs_asterisk_uniqueid_key' in str(e.orig).lower():
                 logger.warning(f"Attempted to log duplicate Asterisk Unique ID: {unique_id}. {e}")
                 raise ValueError(f"Duplicate Asterisk Unique ID: {unique_id}") # Or just return None/False?
            else:
                 logger.error(f"Database integrity error logging call {unique_id}: {e}")
                 raise ValueError("Database integrity error logging call.")
        except Exception as e:
            session.rollback()
            # Log error e
            logger.exception(f"Unexpected error logging call {unique_id}: {e}") # Use exception for full traceback
            raise ValueError(f"Unexpected error logging call: {e}")
            # raise ServiceError(...)