# app/api/routes/internal_logging.py
# -*- coding: utf-8 -*-
"""
Internal API Route for Logging Call Details (used by Asterisk AGI).
Handles transaction commit/rollback and catches custom service exceptions.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from marshmallow import ValidationError

# Import db for transaction control
from app.extensions import db
# Import Service and custom exceptions
from app.services.call_logging_service import CallLoggingService
from app.utils.exceptions import ServiceError, ValidationError as CustomValidationError, ConflictError, ResourceNotFound
# Import Schemas
from app.api.schemas.call_log_schemas import LogCallRequestSchema, LogCallResponseSchema
# Import Decorators
from app.utils.decorators import internal_api_token_required

# Create Blueprint
internal_logging_bp = Blueprint('internal_logging_api', __name__)

# Instantiate schemas
log_call_request_schema = LogCallRequestSchema()
log_call_response_schema = LogCallResponseSchema()


@internal_logging_bp.route('/log_call', methods=['POST'])
@internal_api_token_required # Secure this endpoint
def log_call_attempt():
    """
    Receives CDR data from Asterisk AGI, logs the call attempt, and commits.
    """
    # Get ID early for logging context if needed
    asterisk_uniqueid = request.json.get('asteriskUniqueid', 'UNKNOWN') if request.is_json else 'UNKNOWN_NO_JSON'
    current_app.logger.debug(f"Received internal log_call request for Asterisk ID: {asterisk_uniqueid}")

    if not request.is_json:
         current_app.logger.error("Internal log_call request received without JSON body.")
         abort(400, description="Invalid request format: Expected JSON.")

    try:
        # Validate incoming JSON data against the schema
        # Schema handles mapping from camelCase keys in JSON to snake_case if needed by service
        cdr_data = log_call_request_schema.load(request.json)
    except ValidationError as err: # Marshmallow validation error
        current_app.logger.warning(f"Invalid CDR data received for {asterisk_uniqueid}: {err.messages}")
        # Return structured validation errors
        return jsonify({"status": "error", "message": "Invalid CDR data", "errors": err.messages}), 400

    try:
        # Call the service layer - adds log and stages counter updates in session
        new_cdr_id = CallLoggingService.log_call(cdr_data)

        # --- Commit Transaction ---
        db.session.commit()
        current_app.logger.info(f"Successfully committed call log {new_cdr_id} for Asterisk ID {asterisk_uniqueid}")

        # Prepare success response AFTER commit
        response_data = {
            "status": "success",
            "message": "CDR logged successfully",
            "cdr_id": new_cdr_id # Use the ID returned by the service
        }
        serialized_response = log_call_response_schema.dump(response_data)
        return jsonify(serialized_response), 201 # Created

    # Catch specific errors raised by the service
    except ConflictError as e: # e.g., Duplicate asterisk_uniqueid
        db.session.rollback()
        current_app.logger.warning(f"Call logging conflict for {asterisk_uniqueid}: {e}")
        abort(409, description=str(e)) # 409 Conflict
    except ResourceNotFound as e: # e.g., Invalid campaign_client_setting_id for counter update
        db.session.rollback()
        current_app.logger.error(f"Call logging resource not found error for {asterisk_uniqueid}: {e}")
        # This might indicate a data consistency issue or problem in Asterisk passing IDs
        abort(404, description=str(e)) # Or maybe 400 Bad Request if ID came from request?
    except (CustomValidationError, ServiceError) as e: # Catch validation or DB errors from service
         db.session.rollback()
         current_app.logger.error(f"Call logging service error for {asterisk_uniqueid}: {e}", exc_info=True)
         status_code = 400 if isinstance(e, CustomValidationError) else 500
         abort(status_code, description=str(e))
    except Exception as e: # Catch any other unexpected errors
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error during log_call processing for {asterisk_uniqueid}: {e}")
        abort(500, description="Internal server error during call logging.")