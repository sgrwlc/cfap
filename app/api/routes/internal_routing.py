# -*- coding: utf-8 -*-
"""
Internal API Route for Call Routing Information (used by Asterisk AGI).
"""
from flask import Blueprint, request, jsonify, current_app, abort
from marshmallow import ValidationError

from app.services.call_routing_service import CallRoutingService
from app.api.schemas.routing_schemas import RouteInfoResponseSchema
from app.utils.decorators import internal_api_token_required # Import the security decorator

# Create Blueprint
internal_routing_bp = Blueprint('internal_routing_api', __name__)

# Instantiate response schema for serialization
route_info_schema = RouteInfoResponseSchema()

@internal_routing_bp.route('/route_info', methods=['GET'])
@internal_api_token_required # Secure this endpoint
def get_route_info():
    """
    Provides call routing information based on the dialed DID.
    Requires 'did' query parameter.
    """
    did_number = request.args.get('did')
    if not did_number:
        current_app.logger.warning("Internal route_info request missing 'did' query parameter.")
        abort(400, description="Missing 'did' query parameter.") # Bad Request

    current_app.logger.debug(f"Processing internal route_info request for DID: {did_number}")

    try:
        # Call the service layer to get routing decision
        routing_result = CallRoutingService.get_routing_info(did_number)

        # Validate and serialize the response using Marshmallow schema
        serialized_result = route_info_schema.dump(routing_result)

        # Determine HTTP status code based on service result
        status_code = 200 if routing_result.get('status') == 'proceed' else 404 # Not Found if rejected (or use 4xx specific code?)

        return jsonify(serialized_result), status_code

    except ValueError as e: # Catch potential validation/lookup errors from service
        current_app.logger.error(f"ValueError during route_info for DID {did_number}: {e}")
        # Return a generic internal error to Asterisk, or a more specific one if safe
        abort(500, description=f"Error processing routing request: {e}")
    except Exception as e:
        current_app.logger.exception(f"Unexpected error during route_info for DID {did_number}: {e}")
        abort(500, description="Internal server error processing routing request.")