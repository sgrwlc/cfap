# app/utils/decorators.py
# -*- coding: utf-8 -*-
"""Custom helper decorators for Flask routes."""

from functools import wraps
from flask import current_app, request, abort # Use abort for standard error handling
from flask_login import current_user

# --- Role-Based Access Control ---

def role_required(role_name):
    """
    Decorator factory to ensure the logged-in user has the required role(s).

    Checks for authentication, required role, and active user status.
    Uses abort() to trigger standard HTTP error responses.

    Args:
        role_name (str or list/tuple): The required role name (e.g., 'admin')
                                       or a list/tuple of allowed role names (e.g., ['admin', 'staff']).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Check Authentication (Flask-Login's @login_required handles this implicitly usually,
            #    but explicit check here provides clearer logs before role check)
            if not current_user.is_authenticated:
                current_app.logger.info(f"Permission denied for {request.endpoint}: User not authenticated.")
                abort(401, description="Authentication required.") # Unauthorized

            # 2. Check Role
            allowed_roles = role_name if isinstance(role_name, (list, tuple)) else [role_name]
            user_role = getattr(current_user, 'role', None) # Safely get role

            if user_role not in allowed_roles:
                 current_app.logger.warning(
                     f"Forbidden access attempt to {request.endpoint}: User '{current_user.username}' "
                     f"(Role: {user_role}) does not have required role(s): {allowed_roles}"
                 )
                 abort(403, description=f"Access forbidden: Required role(s) {allowed_roles} not met.") # Forbidden

            # 3. Check Active Status (Belt-and-suspenders check, user_loader might handle this)
            if not current_user.is_active:
                 current_app.logger.warning(f"Forbidden access attempt to {request.endpoint}: User '{current_user.username}' is inactive.")
                 abort(403, description="Access forbidden: User account is inactive.") # Forbidden

            # If all checks pass, proceed to the original view function
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Convenience Decorators for Specific Roles ---

def admin_required(f):
    """Decorator requires 'admin' role."""
    return role_required('admin')(f)

def staff_required(f):
    """Decorator requires 'admin' or 'staff' role."""
    # Staff often have overlapping permissions with Admin. Adjust if needed.
    return role_required(['admin', 'staff'])(f)

def seller_required(f):
    """Decorator requires 'user' role (representing Call Sellers)."""
    return role_required('user')(f)


# --- Internal API Security ---

def internal_api_token_required(f):
    """
    Decorator to verify a secret token for internal API calls (e.g., from Asterisk).
    Checks the 'X-Internal-API-Token' header against the app's configured token.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        expected_token = current_app.config.get('INTERNAL_API_TOKEN')
        provided_token = request.headers.get('X-Internal-API-Token') # Standard header name

        # Check if the token is configured in the application
        if not expected_token:
             current_app.logger.critical(f"Internal API token not configured for endpoint {request.endpoint}. Denying access.")
             abort(500, description="Internal server configuration error: API token missing.") # Misconfiguration

        # Check if the provided token matches the expected one
        # Compare using a secure method if timing attacks are a concern (less critical for internal API)
        if not provided_token or provided_token != expected_token:
            current_app.logger.warning(f"Unauthorized internal API access attempt to {request.endpoint}: Invalid or missing token.")
            abort(401, description="Invalid or missing internal API token.") # Unauthorized

        # If token is valid, proceed to the original view function
        return f(*args, **kwargs)
    return decorated_function