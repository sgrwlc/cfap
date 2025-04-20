# -*- coding: utf-8 -*-
"""
Authentication API Routes
Provides login/logout endpoints.
"""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user

from app.services.auth_service import AuthService
# from app.api.schemas.auth_schemas import LoginSchema # Import schema when created

# Create Blueprint
# Note: We are naming the blueprint 'auth_api' to avoid potential clashes if
# a web UI auth blueprint named 'auth' is added later.
auth_bp = Blueprint('auth_api', __name__)

# Instantiating schema for request validation (Example - uncomment when schema exists)
# login_schema = LoginSchema()

@auth_bp.route('/login', methods=['POST'])
def login():
    """User Login Endpoint."""
    # Validation using Marshmallow/Pydantic schema (Recommended)
    # try:
    #     data = login_schema.load(request.json)
    # except ValidationError as err:
    #     return jsonify(err.messages), 400
    # username = data.get('username')
    # password = data.get('password')

    # Basic validation without schema for now
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
         return jsonify({"message": "Username and password are required."}), 400

    username = data.get('username')
    password = data.get('password')

    user = AuthService.authenticate_user(username, password)

    if user:
        # Log the user in using Flask-Login
        # remember=True keeps the user logged in across browser sessions
        login_user(user, remember=True)
        current_app.logger.info(f"User '{username}' logged in successfully.")
        # Return user info (customize as needed, use a schema for serialization)
        user_data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "status": user.status,
            "full_name": user.full_name,
            "company_name": user.company_name
        }
        return jsonify({
            "message": "Login successful.",
            "user": user_data
        }), 200
    else:
        current_app.logger.warning(f"Failed login attempt for username: '{username}'.")
        return jsonify({"message": "Invalid username or password, or inactive account."}), 401

@auth_bp.route('/logout', methods=['POST'])
@login_required # Ensure user is logged in to log out
def logout():
    """User Logout Endpoint."""
    user_id = current_user.id
    username = current_user.username
    logout_user()
    current_app.logger.info(f"User '{username}' (ID: {user_id}) logged out.")
    return jsonify({"message": "Logout successful."}), 200

@auth_bp.route('/status', methods=['GET'])
@login_required # Check authentication status
def status():
    """Check Login Status Endpoint."""
    # Return current user info (customize, use schema)
    user_data = {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "status": current_user.status,
        "full_name": current_user.full_name,
        "company_name": current_user.company_name
    }
    return jsonify({
        "message": "User is logged in.",
        "logged_in": True,
        "user": user_data
    }), 200

# --- Optional: Add routes for registration (if not admin-only), password reset, etc. ---