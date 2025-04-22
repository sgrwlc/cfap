# app/utils/exceptions.py
# -*- coding: utf-8 -*-
"""
Custom Exception Classes for the Application.

These exceptions are used to signal specific error conditions from the service layer
to the API layer (routes), allowing for more specific error handling and
mapping to appropriate HTTP status codes.
"""

class ServiceError(Exception):
    """Base class for service layer exceptions."""
    status_code = 500  # Default to Internal Server Error
    message = "An unexpected service error occurred."

    def __init__(self, message=None, status_code=None):
        super().__init__(message or self.message)
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self):
        return {"message": str(self)}


class ResourceNotFound(ServiceError):
    """Raised when a requested resource is not found."""
    status_code = 404
    message = "The requested resource was not found."


class ValidationError(ServiceError):
    """Raised for general data validation errors (beyond schema validation)."""
    status_code = 400
    message = "Validation failed."
    # Optionally include more details
    # def __init__(self, errors=None, message=None):
    #     super().__init__(message or self.message, status_code=400)
    #     self.errors = errors or {}
    # def to_dict(self):
    #     return {"message": str(self), "errors": self.errors}


class ConflictError(ServiceError):
    """Raised when an operation conflicts with the current state (e.g., duplicate)."""
    status_code = 409
    message = "A conflict occurred with the current state of the resource."


class AuthorizationError(ServiceError):
    """Raised when a user is not authorized to perform an action."""
    status_code = 403
    message = "You are not authorized to perform this action."


class AuthenticationError(ServiceError):
    """Raised for authentication failures (e.g., invalid credentials, inactive user)."""
    status_code = 401
    message = "Authentication failed."


# Example of a more specific error if needed:
# class UserInactiveError(AuthenticationError):
#     message = "User account is inactive."

# Add more specific exceptions as needed during development.