# -*- coding: utf-8 -*-
"""
Internal API Route for Logging Call Details (used by Asterisk AGI).
"""
from flask import Blueprint, request, jsonify, current_app, abort
from marshmallow import ValidationError

from app.services.call_logging_service import CallLoggingService
from app.api.schemas.call_log_schemas import LogCallRequestSchema, LogCallResponseSchema
from app.utils.decorators import internal_api_token_required # Import the security decorator

# Create Blueprint
internal_logging_bp = Blueprint('internal_logging_api', __name__)

# Instantiate schemas
log_call_request_schema = LogCallRequestSchema()
log_call_response_schema = LogCallResponseSchema()

@internal_logging_bp.route('/log_call', methods=['POST'])
@internal_api_token_required # Secure this endpoint
def log_call_attempt():
    """
    Receives CDR data from Asterisk AGI and logs the call attempt.
    """
    asterisk_uniqueid = request.json.get('asteriskUniqueid', 'UNKNOWN') # Get ID early for logging
    current_app.logger.debug(f"Received internal log_call request for Asterisk ID: {asterisk_uniqueid}")

    try:
        # Validate incoming JSON data against the schema
        cdr_data = log_call_request_schema.load(request.json)
    except ValidationError as err:
        current_app.logger.warning(f"Invalid CDR data received for {asterisk_uniqueid}: {err.messages}")
        abort(400, description=f"Invalid CDR data: {err.messages}") # Bad Request

    try:
        # Call the service layer to log the call and update counters
        new_cdr_id = CallLoggingService.log_call(cdr_data)

        if new_cdr_id:
            response_data = {
                "status": "success",
                "message": "CDR logged successfully",
                "cdr_id": new_cdr_id
            }
            status_code = 201 # Created
        else:
            # This case might occur if service handles duplicate ID gracefully without raising error
             response_data = {
                "status": "error",
                "message": "CDR logging failed (e.g., duplicate ID or internal issue)."
             }
             status_code = 409 # Conflict or 500?

        # Serialize the response
        serialized_response = log_call_response_schema.dump(response_data)
        return jsonify(serialized_response), status_code

    except ValueError as e: # Catch errors raised by the service (e.g., duplicate ID, DB errors)
        current_app.logger.error(f"ValueError during log_call for {asterisk_uniqueid}: {e}")
        # Use 409 Conflict for specific errors like duplicates if distinguishable
        status_code = 409 if "Duplicate" in str(e) else 500
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error during log_call for {asterisk_uniqueid}: {e}")
        abort(500, description="Internal server error during call logging.")