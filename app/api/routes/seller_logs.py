# app/api/routes/seller_logs.py
# -*- coding: utf-8 -*-
"""
Seller API Routes for viewing Call Logs.
Relies on SQLAlchemy query capabilities for filtering, avoids direct pre-validation queries.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from sqlalchemy.orm import joinedload, contains_eager # Use contains_eager for optimized filtering joins
from sqlalchemy import func, select # Import select for potential subqueries if needed
from datetime import datetime, timedelta, timezone

# Import Models (needed for query construction)
from app.database.models.call_log import CallLogModel
from app.database.models.campaign import CampaignModel
from app.database.models.client import ClientModel
from app.database.models.did import DidModel
# Import Decorators
from app.utils.decorators import seller_required
# Import Schemas
from app.api.schemas.call_log_schemas import CallLogListSchema
# Import db extension (needed for paginate)
from app.extensions import db


# Create Blueprint
seller_logs_bp = Blueprint('seller_logs_api', __name__)

# Instantiate schemas
call_log_list_schema = CallLogListSchema()


@seller_logs_bp.route('', methods=['GET'])
@seller_required
def seller_get_call_logs():
    """Seller: Get list of own call logs (paginated and filterable)."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int) # Default 50 for logs

        # --- Filtering ---
        # Start with base query for logs owned by the current user
        query = db.session.query(CallLogModel).filter(CallLogModel.user_id == current_user.id)

        # Eager load related entities needed for response schema and filtering
        query = query.options(
                        joinedload(CallLogModel.campaign),
                        joinedload(CallLogModel.did),
                        joinedload(CallLogModel.client)
                    )

        # Date filtering (example: YYYY-MM-DD format)
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                start_dt_utc = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
                query = query.filter(CallLogModel.timestamp_start >= start_dt_utc)
            except ValueError:
                abort(400, description="Invalid start_date format. Use YYYY-MM-DD.")
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
                end_dt_exclusive_utc = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
                query = query.filter(CallLogModel.timestamp_start < end_dt_exclusive_utc)
            except ValueError:
                 abort(400, description="Invalid end_date format. Use YYYY-MM-DD.")

        # Filter by Campaign ID (Ownership check integrated via base user_id filter)
        campaign_id_filter = request.args.get('campaign_id', type=int)
        if campaign_id_filter:
            # Check existence implicitly by filtering on the relationship's ID
            query = query.filter(CallLogModel.campaign_id == campaign_id_filter)
            # If we need to *strictly* ensure the campaign itself exists and is owned by the user,
            # an explicit join could be added, but the base user_id filter on logs is usually sufficient.
            # query = query.join(CampaignModel, CallLogModel.campaign_id == CampaignModel.id)\
            #              .filter(CampaignModel.user_id == current_user.id) # Redundant if base filter used

        # Filter by DID ID (Ownership check integrated via base user_id filter)
        did_id_filter = request.args.get('did_id', type=int)
        if did_id_filter:
            query = query.filter(CallLogModel.did_id == did_id_filter)
            # Similar to campaign, explicit join could be used for strict check:
            # query = query.join(DidModel, CallLogModel.did_id == DidModel.id)\
            #              .filter(DidModel.user_id == current_user.id) # Redundant

        # Filter by Client ID (No direct ownership, just filter by client involved in user's logs)
        client_id_filter = request.args.get('client_id', type=int)
        if client_id_filter:
            # Simply filter logs that involved this client ID.
            # We don't need to check if the client *exists* separately,
            # as logs will only have IDs for clients that existed at the time.
            query = query.filter(CallLogModel.client_id == client_id_filter)

        # Filter by Call Status (Exact Match, Case-Sensitive depends on DB collation)
        status_filter = request.args.get('call_status', type=str)
        if status_filter:
            # Optionally validate status against known values if desired
            # known_statuses = [...]
            # if status_filter not in known_statuses: abort(400, ...)
            query = query.filter(CallLogModel.call_status == status_filter)
            # Case-insensitive exact match:
            # query = query.filter(func.lower(CallLogModel.call_status) == func.lower(status_filter))

        # Apply ordering (Newest first)
        query = query.order_by(CallLogModel.timestamp_start.desc())

        # --- Query Execution ---
        # Paginate the final query
        # Using select=True is good practice with paginate for SQLAlchemy 2.0+ session queries
        paginated_logs = query.paginate(page=page, per_page=per_page, error_out=False, count=True)

        # Prepare data for serialization
        result_data = {
            'items': paginated_logs.items,
            'page': paginated_logs.page,
            'per_page': paginated_logs.per_page, # Use attribute name
            'total': paginated_logs.total,
            'pages': paginated_logs.pages
        }
        # Schema handles output key mapping ('perPage')
        return jsonify(call_log_list_schema.dump(result_data)), 200

    # --- MODIFY this except block ---
    except Exception as e:
        # --- ADD this check ---
        # Do not intercept HTTP exceptions raised by abort()
        from werkzeug.exceptions import HTTPException # Local import ok here
        if isinstance(e, HTTPException):
            raise e
        # --- END ADD ---

        # Log and return 500 for other unexpected errors
        current_app.logger.exception(f"Unexpected error fetching call logs for user {current_user.id}: {e}")
        abort(500, description="Could not fetch call logs.")