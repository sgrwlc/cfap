# app/api/routes/internal_routing.py
# -*- coding: utf-8 -*-
"""
Internal API Route for Call Routing Information (used by Asterisk AGI).
Handles potential errors from the CallRoutingService.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from marshmallow import ValidationError # Although no request schema used here yet

# Import Service and custom exceptions it might raise (ServiceError)
from app.services.call_routing_service import CallRoutingService
from app.utils.exceptions import ServiceError
# Import Schemas
from app.api.schemas.routing_schemas import RouteInfoResponseSchema
# Import Decorators
from app.utils.decorators import internal_api_token_required

# Create Blueprint
internal_routing_bp = Blueprint('internal_routing_api', __name__)

# Instantiate response schema for serialization
route_info_schema = RouteInfoResponseSchema()


@internal_routing_bp.route('/route_info', methods=['GET'])
@internal_api_token_required # Secure this endpoint
def get_route_info():
    """
    Provides call routing information based on the dialed DID.
    Requires 'did' query parameter. Returns structured routing info or reject reason.
    """
    did_number = request.args.get('did')
    if not did_number:
        current_app.logger.warning("Internal route_info request missing 'did' query parameter.")
        abort(400, description="Missing 'did' query parameter.") # Bad Request

    current_app.logger.debug(f"Processing internal route_info request for DID: {did_number}")

    try:
        # Call the service layer to get routing decision
        # Service now returns a dict: {'status': 'proceed'/'reject', ...}
        routing_result = CallRoutingService.get_routing_info(did_number)

        # Service handles logging internally for reject reasons

        # Validate and serialize the response using Marshmallow schema
        # The schema handles including/excluding fields based on 'status' implicitly
        # if structured correctly (e.g., using required=False on optional fields).
        serialized_result = route_info_schema.dump(routing_result)

        # Determine HTTP status code based on service result 'status' key
        if routing_result.get('status') == 'proceed':
             status_code = 200 # OK
        elif routing_result.get('status') == 'reject':
             # Use 4xx status code for rejections that Asterisk might handle.
             # 404 Not Found is reasonable if no route exists.
             status_code = 404
             # Log the rejection reason for server-side tracking if not logged by service
             # current_app.logger.info(f"Rejecting call to DID {did_number}: {routing_result.get('reject_reason', 'Unknown reason')}")
        else:
             # Should not happen if service behaves correctly
             current_app.logger.error(f"Routing service returned unexpected status for DID {did_number}: {routing_result.get('status')}")
             status_code = 500 # Internal Server Error

        return jsonify(serialized_result), status_code

    except ServiceError as e: # Catch unexpected DB errors from service
        current_app.logger.error(f"ServiceError during route_info for DID {did_number}: {e}", exc_info=True)
        # Return a generic 500 error to Asterisk to indicate internal failure
        abort(500, description="Internal server error processing routing request.")
    except Exception as e: # Catch any other unexpected errors
        current_app.logger.exception(f"Unexpected error during route_info for DID {did_number}: {e}")
        abort(500, description="Internal server error processing routing request.")