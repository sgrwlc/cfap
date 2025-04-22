# -*- coding: utf-8 -*-
"""
Admin API Routes for User Management.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from marshmallow import ValidationError
# sqlalchemy.orm import joinedload # Not currently used, can remove if desired

# Import db for transaction control
from app.extensions import db
# Import Service
from app.services.user_service import UserService
# Import Decorators
from app.utils.decorators import admin_required # Use the admin decorator
# Import Schemas
from app.api.schemas.user_schemas import (
    UserSchema, CreateUserSchema, UpdateUserSchema, ChangePasswordSchema, UserListSchema
)


# Create Blueprint
admin_users_bp = Blueprint('admin_users_api', __name__)

# Instantiate schemas
user_schema = UserSchema()
users_schema = UserSchema(many=True)
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
        return jsonify({"errors": err.messages}), 400 # Return validation errors

    try:
        # Call service - adds user to session, may flush
        new_user = UserService.create_user(**data)

        # --- Commit transaction here in the route handler ---
        try:
            db.session.commit()
            current_app.logger.info(f"Admin {current_user.id} successfully created user {new_user.id} ('{new_user.username}')")
            # Serialize response AFTER successful commit
            return jsonify(user_schema.dump(new_user)), 201 # Created
        except Exception as commit_err:
            db.session.rollback() # Rollback on commit error
            current_app.logger.exception(f"Database commit error creating user: {commit_err}")
            abort(500, description="Database error during user creation.")
        # --- End Commit Logic ---

    except ValueError as e: # Catch errors from service validation/flush
        db.session.rollback() # Ensure rollback if service failed before commit attempt
        current_app.logger.error(f"Admin create user service error: {e}")
        status_code = 409 if 'already exists' in str(e).lower() else 400
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors during service call
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error creating user: {e}")
        abort(500, description="Could not create user due to an internal error.")


@admin_users_bp.route('', methods=['GET'])
@admin_required
def admin_get_users():
    """Admin: Get list of users (paginated)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    try:
        paginated_users = UserService.get_all_users(page=page, per_page=per_page)
        # Prepare data structure matching the List schema, using attribute names
        result_data = {
            'items': paginated_users.items,
            'page': paginated_users.page,
            'per_page': paginated_users.per_page, # Source attribute name
            'total': paginated_users.total,
            'pages': paginated_users.pages
        }
        # Schema maps 'per_page' attribute to 'perPage' output key
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
        # Validate input data (allows partial updates)
        data_to_update = update_user_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin update user validation error for ID {user_id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    if not data_to_update:
         abort(400, description="No valid fields provided for update.")

    try:
        # Call service - updates object in session but SHOULD NOT COMMIT
        updated_user = UserService.update_user(user_id, **data_to_update)

        # --- Commit transaction here in the route handler ---
        try:
            db.session.commit()
            current_app.logger.info(f"Admin {current_user.id} successfully updated user {user_id}")
            # Return the updated user data after successful commit
            # Re-fetch or dump the object returned by service (depends if service returns committed state)
            # Dumping returned object is usually fine if service flushed.
            return jsonify(user_schema.dump(updated_user)), 200
        except Exception as commit_err:
            db.session.rollback()
            current_app.logger.exception(f"Database commit error updating user {user_id}: {commit_err}")
            abort(500, description="Database error during user update.")
        # --- End Commit Logic ---

    except ValueError as e: # Catch specific service errors (not found, validation, flush error)
        db.session.rollback()
        current_app.logger.error(f"Admin update user service error for ID {user_id}: {e}")
        status_code = 404 if 'not found' in str(e).lower() else (409 if 'in use' in str(e).lower() else 400)
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors during service call
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
        # Validate input using password schema
        data = change_password_schema.load(json_data)
    except ValidationError as err:
        current_app.logger.warning(f"Admin change password validation error for ID {user_id}: {err.messages}")
        return jsonify({"errors": err.messages}), 400

    try:
        # Call service - updates password hash in session but SHOULD NOT COMMIT
        # Assume service returns True/False or raises ValueError on not found
        success = UserService.change_password(user_id, data['password'])

        if not success: # If service explicitly returned False for some reason
             db.session.rollback() # Ensure rollback
             abort(500, description="Password update failed in service layer.")

        # --- Commit transaction here in the route handler ---
        try:
            db.session.commit()
            current_app.logger.info(f"Admin {current_user.id} successfully changed password for user {user_id}")
            return jsonify({"message": "Password updated successfully."}), 200
        except Exception as commit_err:
            db.session.rollback()
            current_app.logger.exception(f"Database commit error changing password for user {user_id}: {commit_err}")
            abort(500, description="Database error during password change.")
        # --- End Commit Logic ---

    except ValueError as e: # Catches user not found or DB errors from service flush/pre-checks
         db.session.rollback()
         current_app.logger.error(f"Admin change password service error for ID {user_id}: {e}")
         status_code = 404 if 'not found' in str(e).lower() else 500
         abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors during service call
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
        # Call service - marks user for deletion in session but SHOULD NOT COMMIT
        # Assume service returns True or raises ValueError on not found/failure
        success = UserService.delete_user(user_id)

        if not success: # If service explicitly returned False
             db.session.rollback()
             abort(500, description="User deletion failed in service layer.")

        # --- Commit transaction here in the route handler ---
        try:
            db.session.commit()
            current_app.logger.info(f"Admin {current_user.id} successfully deleted user {user_id}")
            return '', 204 # No Content
        except Exception as commit_err:
            db.session.rollback()
            current_app.logger.exception(f"Database commit error deleting user {user_id}: {commit_err}")
            abort(500, description="Database error during user deletion.")
        # --- End Commit Logic ---

    except ValueError as e: # Catches user not found or DB errors from service flush/pre-checks
        db.session.rollback()
        current_app.logger.error(f"Admin delete user service error for ID {user_id}: {e}")
        status_code = 404 if 'not found' in str(e).lower() else 500
        abort(status_code, description=str(e))
    except Exception as e: # Catch unexpected errors during service call
        db.session.rollback()
        current_app.logger.exception(f"Unexpected error deleting user {user_id}: {e}")
        abort(500, description="Could not delete user due to an internal error.")