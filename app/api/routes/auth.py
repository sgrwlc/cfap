# app/api/routes/auth.py
# -*- coding: utf-8 -*-
"""
Authentication API Routes
Provides login/logout endpoints.
"""
from flask import Blueprint, request, jsonify, current_app, abort # Added abort
from flask_login import login_user, logout_user, login_required, current_user
from marshmallow import Schema, fields, ValidationError # Added Marshmallow imports for basic validation schema

# Import service and custom exception
from app.services.auth_service import AuthService
from app.utils.exceptions import AuthenticationError

# Import base user schema for response serialization consistency
from app.api.schemas.user_schemas import UserSchema


# --- Basic Login Schema ---
class LoginSchema(Schema):
    username = fields.Str(required=True)
    password = fields.Str(required=True)

# Create Blueprint
auth_bp = Blueprint('auth_api', __name__)

# Instantiate schemas
login_request_schema = LoginSchema()
user_response_schema = UserSchema() # Use the existing UserSchema for response

@auth_bp.route('/login', methods=['POST'])
def login():
    """User Login Endpoint."""
    json_data = request.get_json()
    if not json_data:
        # Use abort for standard error handling
        abort(400, description="No input data provided.")

    # Validate request body using Marshmallow schema
    try:
        data = login_request_schema.load(json_data)
    except ValidationError as err:
        # Return validation errors in a structured format
        return jsonify({"errors": err.messages}), 400

    username = data['username']
    password = data['password']

    try:
        # Call the authentication service
        user = AuthService.authenticate_user(username, password)

        # User authenticated successfully by the service
        # Log the user in using Flask-Login
        login_user(user, remember=True) # 'remember=True' sets persistent cookie
        current_app.logger.info(f"User '{username}' (ID: {user.id}) logged in successfully.")

        # Prepare and serialize user data for the response using UserSchema
        user_data = user_response_schema.dump(user)

        return jsonify({
            "message": "Login successful.",
            "user": user_data
        }), 200

    except AuthenticationError as e:
        # Catch specific authentication errors from the service
        current_app.logger.warning(f"Failed login attempt for username '{username}': {e}")
        # Return a 401 Unauthorized status code with the error message from the exception
        # Abort generates the JSON response automatically based on the message
        abort(401, description=str(e))
    except Exception as e:
        # Catch any other unexpected errors during the process
        current_app.logger.exception(f"Unexpected error during login for username '{username}': {e}")
        abort(500, description="An unexpected error occurred during login.")


@auth_bp.route('/logout', methods=['POST'])
@login_required # Ensures only logged-in users can logout
def logout():
    """User Logout Endpoint."""
    user_id = current_user.id
    username = current_user.username

    logout_user() # Clears the user session

    current_app.logger.info(f"User '{username}' (ID: {user_id}) logged out.")
    return jsonify({"message": "Logout successful."}), 200


@auth_bp.route('/status', methods=['GET'])
@login_required # Ensures only logged-in users can check status
def status():
    """Check Login Status Endpoint."""
    # User is authenticated if this point is reached due to @login_required

    # Serialize current user data using UserSchema
    user_data = user_response_schema.dump(current_user)

    return jsonify({
        "message": "User is logged in.",
        "logged_in": True,
        "user": user_data
    }), 200

# Note: Flask-Login's @login_manager.unauthorized_handler in app/__init__.py
# handles cases where @login_required fails, returning a 401 response.