# -*- coding: utf-8 -*-
"""
Admin API Routes for User Management.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from marshmallow import ValidationError
from sqlalchemy.orm import joinedload # If needed for eager loading

from app.services.user_service import UserService
from app.utils.decorators import admin_required # Use the admin decorator
from app.api.schemas.user_schemas import (
    UserSchema, CreateUserSchema, UpdateUserSchema, ChangePasswordSchema, UserListSchema
)
from app.extensions import db # Import db if using pagination directly

# Create Blueprint
admin_users_bp = Blueprint('admin_users_api', __name__)

# Instantiate schemas
user_schema = UserSchema()
users_schema = UserSchema(many=True) # For lists without pagination meta
create_user_schema = CreateUserSchema()
update_user_schema = UpdateUserSchema()
change_password_schema = ChangePasswordSchema()
user_list_schema = UserListSchema()

@admin_users_bp.route('', methods=['POST'])
@admin_required
def admin_create_user():
    """Admin: Create a new user."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        # Validate and deserialize input
        data = create_user_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin create user validation error: {err.messages}")
        return jsonify(err.messages), 400

    try:
        # Call service to create user
        new_user = UserService.create_user(**data)
        # Serialize response
        return jsonify(user_schema.dump(new_user)), 201 # Created
    except ValueError as e:
        current_app.logger.error(f"Admin create user error: {e}")
        # Check for specific errors like duplicates
        status_code = 409 if 'already exists' in str(e) else 400
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error creating user: {e}")
        abort(500, description="Could not create user.")


@admin_users_bp.route('', methods=['GET'])
@admin_required
def admin_get_users():
    """Admin: Get list of users (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    try:
        paginated_users = UserService.get_all_users(page=page, per_page=per_page)
        # Serialize response using pagination schema
        result = user_list_schema.dump({
        'items': paginated_users.items,
        'page': paginated_users.page,
        'per_page': paginated_users.per_page, # Still pass the attribute name
        'total': paginated_users.total,
        'pages': paginated_users.pages
    })
        return jsonify(result), 200
    except Exception as e:
        current_app.logger.exception(f"Unexpected error fetching users: {e}")
        abort(500, description="Could not fetch users.")


@admin_users_bp.route('/<int:user_id>', methods=['GET'])
@admin_required
def admin_get_user(user_id):
    """Admin: Get details for a specific user."""
    user = UserService.get_user_by_id(user_id)
    if not user:
        abort(404, description=f"User with ID {user_id} not found.")

    return jsonify(user_schema.dump(user)), 200


@admin_users_bp.route('/<int:user_id>', methods=['PUT'])
@admin_required
def admin_update_user(user_id):
    """Admin: Update user details (email, role, status, names)."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    # Prevent admin from modifying themselves this way? Optional check.
    # if user_id == current_user.id:
    #     abort(403, description="Admin cannot modify own basic details via this endpoint. Use profile settings.")

    try:
        # Validate input data (allows partial updates)
        data_to_update = update_user_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin update user validation error for ID {user_id}: {err.messages}")
        return jsonify(err.messages), 400

    if not data_to_update:
         abort(400, description="No valid fields provided for update.")

    try:
        updated_user = UserService.update_user(user_id, **data_to_update)
        return jsonify(user_schema.dump(updated_user)), 200
    except ValueError as e:
        current_app.logger.error(f"Admin update user error for ID {user_id}: {e}")
        status_code = 404 if 'not found' in str(e) else (409 if 'in use' in str(e) else 400)
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error updating user {user_id}: {e}")
        abort(500, description="Could not update user.")


@admin_users_bp.route('/<int:user_id>/password', methods=['PUT'])
@admin_required
def admin_change_user_password(user_id):
    """Admin: Change a user's password."""
    json_data = request.get_json()
    if not json_data:
        abort(400, description="No input data provided.")

    try:
        data = change_password_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin change password validation error for ID {user_id}: {err.messages}")
        return jsonify(err.messages), 400

    try:
        success = UserService.change_password(user_id, data['password'])
        if success:
            return jsonify({"message": "Password updated successfully."}), 200
        else:
             # Should not happen if service raises ValueError, but as fallback
             abort(500, description="Password update failed for an unknown reason.")
    except ValueError as e: # Catches user not found or DB errors from service
         current_app.logger.error(f"Admin change password error for ID {user_id}: {e}")
         status_code = 404 if 'not found' in str(e) else 500
         abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error changing password for user {user_id}: {e}")
        abort(500, description="Could not change password.")


@admin_users_bp.route('/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    """Admin: Delete a user."""
    if user_id == current_user.id:
        abort(403, description="Admin cannot delete their own account.")

    try:
        success = UserService.delete_user(user_id)
        if success:
            return '', 204 # No Content
        else:
             # Should not happen if service raises ValueError
             abort(500, description="User deletion failed for an unknown reason.")
    except ValueError as e: # Catches user not found or DB errors from service
        current_app.logger.error(f"Admin delete user error for ID {user_id}: {e}")
        status_code = 404 if 'not found' in str(e) else 500
        abort(status_code, description=str(e))
    except Exception as e:
        current_app.logger.exception(f"Unexpected error deleting user {user_id}: {e}")
        abort(500, description="Could not delete user.")