# -*- coding: utf-8 -*-
"""
Seller API Routes for viewing Call Logs.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from sqlalchemy.orm import joinedload
# --- Added func for potential case-insensitive exact match ---
from sqlalchemy import func
from datetime import datetime, timedelta, timezone # Use timezone for explicit UTC comparison

from app.database.models.call_log import CallLogModel
from app.database.models.campaign import CampaignModel # For filtering checks
from app.database.models.client import ClientModel # For filtering checks
from app.database.models.did import DidModel # For filtering checks
from app.utils.decorators import seller_required
from app.api.schemas.call_log_schemas import CallLogSchema, CallLogListSchema
from app.extensions import db # Needed for pagination

# Create Blueprint
seller_logs_bp = Blueprint('seller_logs_api', __name__)

# Instantiate schemas
# call_log_schema = CallLogSchema() # Only needed if fetching a single log detail
call_log_list_schema = CallLogListSchema()

@seller_logs_bp.route('', methods=['GET'])
@seller_required
def seller_get_call_logs():
    """Seller: Get list of own call logs (paginated and filterable)."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int) # Default 50 for logs

    # --- Filtering ---
    filters = [CallLogModel.user_id == current_user.id] # Base filter: Only own logs
    valid_query = True
    error_message = None

    # Date filtering (example: YYYY-MM-DD format)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    try:
        if start_date_str:
            # Parse date and create timezone-aware datetime for start of day UTC
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            start_dt_utc = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
            filters.append(CallLogModel.timestamp_start >= start_dt_utc)
        if end_date_str:
            # Parse date and create timezone-aware datetime for start of *next* day UTC
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            end_dt_exclusive_utc = datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
            filters.append(CallLogModel.timestamp_start < end_dt_exclusive_utc)
    except ValueError:
        valid_query = False
        error_message = "Invalid date format. Use YYYY-MM-DD."

    # Filter by Campaign ID (check ownership)
    campaign_id_filter = request.args.get('campaign_id', type=int)
    if campaign_id_filter:
        # Verify campaign belongs to user
        campaign_exists = db.session.query(db.exists().where(
            CampaignModel.id == campaign_id_filter,
            CampaignModel.user_id == current_user.id
        )).scalar()
        if campaign_exists:
            filters.append(CallLogModel.campaign_id == campaign_id_filter)
        else:
            valid_query = False
            # Provide specific error message
            error_message = f"Campaign ID {campaign_id_filter} not found or not owned by user."

    # Filter by DID ID (check ownership)
    did_id_filter = request.args.get('did_id', type=int)
    if did_id_filter:
        did_exists = db.session.query(db.exists().where(
            DidModel.id == did_id_filter,
            DidModel.user_id == current_user.id
        )).scalar()
        if did_exists:
            filters.append(CallLogModel.did_id == did_id_filter)
        else:
            valid_query = False
            error_message = f"DID ID {did_id_filter} not found or not owned by user."

    # Filter by Client ID
    client_id_filter = request.args.get('client_id', type=int)
    if client_id_filter:
        # Just check if the client ID exists in the clients table
        client_exists = db.session.query(db.exists().where(
            ClientModel.id == client_id_filter
        )).scalar()
        if client_exists:
            # Apply filter directly to the log's client_id column
            # Base user_id filter ensures we only get seller's logs anyway
            filters.append(CallLogModel.client_id == client_id_filter)
        else:
            valid_query = False
            error_message = f"Client ID {client_id_filter} not found."

    # Filter by Call Status (Exact Match, Case-Sensitive recommended unless DB is CI)
    status_filter = request.args.get('call_status', type=str)
    if status_filter:
        # Use exact match (case-sensitive depends on DB collation)
        filters.append(CallLogModel.call_status == status_filter)
        # Or for case-insensitive exact match:
        # filters.append(func.lower(CallLogModel.call_status) == func.lower(status_filter))

    # --- Query Execution ---
    if not valid_query:
        abort(400, description=error_message)

    try:
        # Base query on CallLogModel
        query = db.session.query(CallLogModel)

        # Apply eager loading options
        query = query.options(
                    joinedload(CallLogModel.campaign),
                    joinedload(CallLogModel.did),
                    joinedload(CallLogModel.client)
                )
        # Apply all collected filters
        query = query.filter(*filters)
        # Apply ordering
        query = query.order_by(CallLogModel.timestamp_start.desc()) # Newest first

        # Paginate the final query
        # Use select=True for paginate with SQLAlchemy >= 2.0 session queries
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

    except Exception as e:
        current_app.logger.exception(f"Unexpected error fetching call logs for user {current_user.id}: {e}")
        abort(500, description="Could not fetch call logs.")