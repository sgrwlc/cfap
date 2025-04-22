# app/api/routes/admin_users.py
# -*- coding: utf-8 -*-
"""
Admin API Routes for User Management.
Handles transaction commit/rollback and catches custom service exceptions.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from marshmallow import ValidationError

# Import db for transaction control
from app.extensions import db
# Import Service and custom exceptions
from app.services.user_service import UserService
# Corrected Import: Added AuthorizationError
from app.utils.exceptions import (
    ResourceNotFound, ConflictError, ServiceError,
    ValidationError as CustomValidationError, AuthorizationError
)
# Import Decorators
from app.utils.decorators import admin_required
# Import Schemas
from app.api.schemas.user_schemas import (
    UserSchema, CreateUserSchema, UpdateUserSchema, ChangePasswordSchema, UserListSchema
)


# Create Blueprint
admin_users_bp = Blueprint('admin_users_api', __name__)

# Instantiate schemas
user_schema = UserSchema()
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
        data = create_user_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin create user validation error: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    try:
        new_user = UserService.create_user(**data)
        db.session.commit()
        current_app.logger.info(f"Admin {current_user.id} successfully created user {new_user.id} ('{new_user.username}')")
        return jsonify(user_schema.dump(new_user)), 201

    except (ConflictError, CustomValidationError) as e:
        db.session.rollback()
        current_app.logger.warning(f"Admin create user failed: {e}")
        status_code = 409 if isinstance(e, ConflictError) else 400
        abort(status_code, description=str(e))
    except ServiceError as e:
        db.session.rollback()
        current_app.logger.error(f"Admin create user service error: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error creating user: {e}")
        abort(500, description="Could not create user due to an internal server error.")


@admin_users_bp.route('', methods=['GET'])
@admin_required
def admin_get_users():
    """Admin: Get list of users (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    try:
        paginated_users = UserService.get_all_users(page=page, per_page=per_page)
        result_data = {
            'items': paginated_users.items,
            'page': paginated_users.page,
            'per_page': paginated_users.per_page,
            'total': paginated_users.total,
            'pages': paginated_users.pages
        }
        return jsonify(user_list_schema.dump(result_data)), 200
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

    try:
        data_to_update = update_user_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin update user validation error for ID {user_id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    if not data_to_update:
         abort(400, description="No valid fields provided for update.")

    try:
        updated_user = UserService.update_user(user_id, **data_to_update)
        db.session.commit()
        current_app.logger.info(f"Admin {current_user.id} successfully updated user {user_id}")
        return jsonify(user_schema.dump(updated_user)), 200

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Admin update user failed: {e}")
        abort(404, description=str(e))
    except (ConflictError, CustomValidationError) as e:
        db.session.rollback()
        current_app.logger.warning(f"Admin update user failed for ID {user_id}: {e}")
        status_code = 409 if isinstance(e, ConflictError) else 400
        abort(status_code, description=str(e))
    except ServiceError as e:
        db.session.rollback()
        current_app.logger.error(f"Admin update user service error for ID {user_id}: {e}", exc_info=True)
        abort(500, description=str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error updating user {user_id}: {e}")
        abort(500, description="Could not update user due to an internal error.")


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
        return jsonify({"errors": err.messages}), 400

    try:
        UserService.change_password(user_id, data['password'])
        db.session.commit()
        current_app.logger.info(f"Admin {current_user.id} successfully changed password for user {user_id}")
        return jsonify({"message": "Password updated successfully."}), 200

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Admin change password failed: {e}")
        abort(404, description=str(e))
    except (CustomValidationError, ServiceError) as e:
         db.session.rollback()
         current_app.logger.error(f"Admin change password service error for ID {user_id}: {e}", exc_info=True)
         status_code = 400 if isinstance(e, CustomValidationError) else 500
         abort(status_code, description=str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error changing password for user {user_id}: {e}")
        abort(500, description="Could not change password due to an internal error.")


@admin_users_bp.route('/<int:user_id>', methods=['DELETE'])
@admin_required
def admin_delete_user(user_id):
    """Admin: Delete a user."""
    if user_id == current_user.id:
        abort(403, description="Admin cannot delete their own account.")

    try:
        UserService.delete_user(user_id)
        db.session.commit()
        current_app.logger.info(f"Admin {current_user.id} successfully deleted user {user_id}")
        return '', 204 # No Content

    except ResourceNotFound as e:
        db.session.rollback()
        current_app.logger.warning(f"Admin delete user failed: {e}")
        abort(404, description=str(e))
    # Corrected: Catching AuthorizationError now that it's imported
    except (AuthorizationError, ServiceError) as e:
        db.session.rollback()
        current_app.logger.error(f"Admin delete user service error for ID {user_id}: {e}", exc_info=True)
        # Map specific exception type to status code
        status_code = 403 if isinstance(e, AuthorizationError) else 500
        abort(status_code, description=str(e))
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error deleting user {user_id}: {e}")
        abort(500, description="Could not delete user due to an internal error.")