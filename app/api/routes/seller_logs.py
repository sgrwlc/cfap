# -*- coding: utf-8 -*-
"""
Seller API Routes for viewing Call Logs.
"""
from flask import Blueprint, request, jsonify, current_app, abort
from flask_login import current_user
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta # For date filtering

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
# call_log_schema = CallLogSchema() # Not needed for list usually
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
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            # Filter for calls started on or after the beginning of start_date (UTC assumed)
            filters.append(CallLogModel.timestamp_start >= datetime.combine(start_date, datetime.min.time(), tzinfo=None)) # Assumes DB stores UTC
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            # Filter for calls started before the beginning of the day *after* end_date
            end_date_exclusive = end_date + timedelta(days=1)
            filters.append(CallLogModel.timestamp_start < datetime.combine(end_date_exclusive, datetime.min.time(), tzinfo=None))
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

    # Filter by Client ID (client doesn't need to be owned by user)
    client_id_filter = request.args.get('client_id', type=int)
    if client_id_filter:
        client_exists = db.session.query(db.exists().where(ClientModel.id == client_id_filter)).scalar()
        if client_exists:
            filters.append(CallLogModel.client_id == client_id_filter)
        else:
            valid_query = False
            error_message = f"Client ID {client_id_filter} not found."

    # Filter by Call Status
    status_filter = request.args.get('call_status', type=str)
    if status_filter:
        filters.append(CallLogModel.call_status.ilike(f"%{status_filter}%")) # Case-insensitive search

    # --- Query Execution ---
    if not valid_query:
        abort(400, description=error_message)

    try:
        query = CallLogModel.query.options(
                    # Eager load related info needed by schema
                    joinedload(CallLogModel.campaign),
                    joinedload(CallLogModel.did),
                    joinedload(CallLogModel.client)
                ).filter(*filters)\
                 .order_by(CallLogModel.timestamp_start.desc()) # Newest first

        paginated_logs = query.paginate(page=page, per_page=per_page, error_out=False)

        result = call_log_list_schema.dump({
            'items': paginated_logs.items,
            'page': paginated_logs.page,
            'per_page': paginated_logs.per_page,
            'total': paginated_logs.total,
            'pages': paginated_logs.pages
        })
        return jsonify(result), 200

    except Exception as e:
        current_app.logger.exception(f"Unexpected error fetching call logs for user {current_user.id}: {e}")
        abort(500, description="Could not fetch call logs.")