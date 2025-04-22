# app/services/call_routing_service.py
# -*- coding: utf-8 -*-
"""
Call Routing Service
Provides logic to determine potential call routing destinations based on DID,
campaign configuration, and client settings/status/caps.
This service is read-only and DOES NOT modify the database state.
"""
import logging # Use standard logging
from sqlalchemy import select, func, and_
from sqlalchemy.orm import joinedload, selectinload, contains_eager
# from flask import current_app # No longer needed at module level

from app.database.models.did import DidModel
from app.database.models.campaign import CampaignModel, CampaignDidModel, CampaignClientSettingsModel
from app.database.models.client import ClientModel
from app.database.models.pjsip import PjsipEndpointModel, PjsipAorModel
from app.extensions import db
from app.utils.exceptions import ServiceError, ValidationError


# Use standard Python logger - Flask will configure handlers
log = logging.getLogger(__name__) # Corrected: Use standard logger


class CallRoutingService:

    @staticmethod
    def get_routing_info(did_number: str) -> dict:
        """
        Determines potential routing targets for an incoming call based on the DID.

        Args:
            did_number (str): The dialed number (DID).

        Returns:
            dict: A dictionary containing either:
                  {'status': 'proceed', 'routing_info': { ... }}
                  or
                  {'status': 'reject', 'reject_reason': 'reason_code'}
                  'routing_info' contains campaign details and an ordered list of
                  eligible targets with their settings and PJSIP details.

        Raises:
             ServiceError: If an unexpected database error occurs during lookup.
        """
        # Use the logger obtained via logging.getLogger
        log.info(f"Routing lookup requested for DID: {did_number}")

        if not did_number:
             log.warning("Routing lookup attempted with empty DID number.")
             return {"status": "reject", "reject_reason": "invalid_did_input"}

        try:
            session = db.session

            # 1. Find the DID and its owner, check statuses
            did_record = session.query(DidModel).options(joinedload(DidModel.owner))\
                               .filter(DidModel.number == did_number)\
                               .one_or_none()

            if not did_record:
                log.warning(f"Routing reject: DID '{did_number}' not found in database.")
                return {"status": "reject", "reject_reason": "did_not_found"}

            if did_record.status != 'active':
                log.warning(f"Routing reject: DID '{did_number}' (ID: {did_record.id}) is inactive.")
                return {"status": "reject", "reject_reason": "did_inactive"}

            if not did_record.owner:
                 log.error(f"Data Integrity Issue: DID {did_record.id} has no owner (user_id: {did_record.user_id}). Rejecting.")
                 return {"status": "reject", "reject_reason": "internal_data_error"}
            if did_record.owner.status != 'active':
                 log.warning(f"Routing reject: Owner (User ID: {did_record.user_id}) of DID '{did_number}' is inactive.")
                 return {"status": "reject", "reject_reason": "owner_inactive"}

            user_id = did_record.user_id
            did_id = did_record.id
            log.debug(f"DID '{did_number}' (ID: {did_id}) found, active, owned by active User ID: {user_id}")

            # 2. Find the Active Campaign linked to this DID for this User
            campaign_link_sq = session.query(CampaignDidModel.campaign_id)\
                                   .filter(CampaignDidModel.did_id == did_id)\
                                   .subquery()

            active_campaign = session.query(CampaignModel).filter(
                CampaignModel.user_id == user_id,
                CampaignModel.status == 'active',
                CampaignModel.id.in_(select(campaign_link_sq))
            ).first()

            if not active_campaign:
                log.warning(f"Routing reject: No active campaign found linked to DID ID {did_id} for User ID {user_id}.")
                return {"status": "reject", "reject_reason": "no_active_campaign_for_did"}

            campaign_id = active_campaign.id
            routing_strategy = active_campaign.routing_strategy
            dial_timeout_seconds = active_campaign.dial_timeout_seconds
            log.debug(f"Active Campaign ID: {campaign_id} found (Strategy: {routing_strategy}, Timeout: {dial_timeout_seconds}s)")

            # 3. Find eligible, active Client Settings for this Campaign with valid PJSIP config
            eligible_settings_query = session.query(
                CampaignClientSettingsModel, ClientModel, PjsipEndpointModel, PjsipAorModel
            ).select_from(CampaignClientSettingsModel)\
                .join(ClientModel, CampaignClientSettingsModel.client_id == ClientModel.id)\
                .join(PjsipEndpointModel, ClientModel.id == PjsipEndpointModel.client_id)\
                .join(PjsipAorModel, ClientModel.id == PjsipAorModel.client_id)\
                .filter(
                    CampaignClientSettingsModel.campaign_id == campaign_id,
                    CampaignClientSettingsModel.status == 'active',
                    ClientModel.status == 'active',
                    PjsipAorModel.contact.isnot(None)
                )

            # Apply ordering based on strategy
            if routing_strategy == 'priority':
                eligible_settings_query = eligible_settings_query.order_by(CampaignClientSettingsModel.forwarding_priority.asc(), CampaignClientSettingsModel.id.asc())
            elif routing_strategy == 'round_robin':
                log.debug("Using simple ID ordering for 'round_robin'. Asterisk needs to implement RR logic.")
                eligible_settings_query = eligible_settings_query.order_by(CampaignClientSettingsModel.id.asc())
            elif routing_strategy == 'weighted':
                 log.debug("Using priority/ID ordering for 'weighted'. Asterisk needs weighted selection logic.")
                 eligible_settings_query = eligible_settings_query.order_by(CampaignClientSettingsModel.forwarding_priority.asc(), CampaignClientSettingsModel.id.asc())
            else:
                 log.warning(f"Unknown routing strategy '{routing_strategy}', defaulting to priority ordering.")
                 eligible_settings_query = eligible_settings_query.order_by(CampaignClientSettingsModel.forwarding_priority.asc(), CampaignClientSettingsModel.id.asc())

            potential_targets_raw = eligible_settings_query.all()

            if not potential_targets_raw:
                log.warning(f"Routing reject: No active clients with valid PJSIP contact found linked to Campaign ID {campaign_id}.")
                return {"status": "reject", "reject_reason": "no_active_clients_in_campaign"}

            # 4. Filter Targets by Total Cap and Format Response Objects
            eligible_targets_list = []
            for setting, client, endpoint, aor in potential_targets_raw:
                total_allowed = setting.total_calls_allowed
                if total_allowed is not None and setting.current_total_calls >= total_allowed:
                    log.info(f"Skipping Client ID {client.id} (Setting ID: {setting.id}) for Campaign {campaign_id}: Total cap ({total_allowed}) reached (Current: {setting.current_total_calls}).")
                    continue

                target_info = {
                    "ccs_id": setting.id, "client_id": client.id, "client_identifier": client.client_identifier,
                    "client_name": client.name, "sip_uri": aor.contact, "max_concurrency": setting.max_concurrency,
                    "weight": setting.weight, "priority": setting.forwarding_priority,
                    "outbound_auth": endpoint.outbound_auth, "callerid_override": endpoint.callerid,
                    "context": endpoint.context, "transport": endpoint.transport
                }
                eligible_targets_list.append(target_info)

            # 5. Check if any targets remain after filtering
            if not eligible_targets_list:
                log.warning(f"Routing reject: No eligible clients remain for Campaign ID {campaign_id} after filtering (e.g., all capped).")
                return {"status": "reject", "reject_reason": "no_eligible_clients_available"}

            # 6. Prepare final 'proceed' response structure
            routing_info_payload = {
                "user_id": user_id, "campaign_id": campaign_id, "did_id": did_id,
                "routing_strategy": routing_strategy, "dial_timeout_seconds": dial_timeout_seconds,
                "targets": eligible_targets_list
            }

            log.info(f"Routing info found for DID '{did_number}'. Strategy: {routing_strategy}. Eligible Targets: {len(eligible_targets_list)}")
            return {"status": "proceed", "routing_info": routing_info_payload}

        except Exception as e:
            log.exception(f"Unexpected error during routing lookup for DID '{did_number}': {e}")
            raise ServiceError(f"Unexpected database error during routing lookup: {e}")