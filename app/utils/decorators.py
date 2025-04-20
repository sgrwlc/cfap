# -*- coding: utf-8 -*-
"""Helper decorators."""

from functools import wraps
from flask import current_app, jsonify, abort
from flask_login import current_user

def role_required(role_name):
    """
    Decorator to ensure the logged-in user has the required role(s).

    Args:
        role_name (str or list/tuple): The required role name or a list/tuple of allowed role names.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Check if user is authenticated
            if not current_user.is_authenticated:
                # Use abort() for standard error handling, customize response if needed
                current_app.logger.warning(f"Unauthorized access attempt to {f.__name__}: User not authenticated.")
                abort(401, description="Authentication required.") # Unauthorized

            # 2. Check if user has the required role
            allowed_roles = role_name if isinstance(role_name, (list, tuple)) else [role_name]
            if not hasattr(current_user, 'role') or current_user.role not in allowed_roles:
                 current_app.logger.warning(
                     f"Forbidden access attempt to {f.__name__}: User '{current_user.username}' "
                     f"(Role: {getattr(current_user, 'role', 'N/A')}) does not have required role(s): {allowed_roles}"
                 )
                 abort(403, description=f"Access forbidden: Required role(s) {allowed_roles} not met.") # Forbidden

            # 3. Check if user account is active (redundant if login loader checks, but good practice)
            if not current_user.is_active:
                 current_app.logger.warning(f"Forbidden access attempt to {f.__name__}: User '{current_user.username}' is inactive.")
                 abort(403, description="Access forbidden: User account is inactive.") # Forbidden

            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Specific role decorators for convenience
def admin_required(f):
    return role_required('admin')(f)

def staff_required(f):
    # Staff can typically do admin tasks too, adjust as needed
    return role_required(['admin', 'staff'])(f)

def seller_required(f):
    # 'user' role represents Call Sellers
    return role_required('user')(f)

# --- Add other decorators as needed ---
# Example: Decorator for checking internal API token

def internal_api_token_required(f):
    """Decorator to verify a secret token for internal API calls."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request # Import request context locally
        expected_token = current_app.config.get('INTERNAL_API_TOKEN')
        provided_token = request.headers.get('X-Internal-API-Token') # Example header name

        if not expected_token:
             current_app.logger.error(f"Internal API token not configured for endpoint {f.__name__}. Denying access.")
             abort(500, description="Internal server configuration error.") # Misconfiguration

        if not provided_token or provided_token != expected_token:
            current_app.logger.warning(f"Unauthorized internal API access attempt to {f.__name__}: Invalid or missing token.")
            abort(401, description="Invalid or missing internal API token.") # Unauthorized

        return f(*args, **kwargs)
    return decorated_function