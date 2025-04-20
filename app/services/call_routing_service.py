# -*- coding: utf-8 -*-
"""
Call Routing Service
Provides logic to determine call routing destinations based on DID,
campaign configuration, and client settings/status/caps.
"""
import logging
from sqlalchemy import select, func, and_
from sqlalchemy.orm import joinedload, selectinload

from app.database.models.did import DidModel
from app.database.models.campaign import CampaignModel, CampaignDidModel, CampaignClientSettingsModel
from app.database.models.client import ClientModel
from app.database.models.pjsip import PjsipEndpointModel, PjsipAorModel
from app.extensions import db

# Configure logging for this service
logger = logging.getLogger(__name__)


class CallRoutingService:

    @staticmethod
    def get_routing_info(did_number: str) -> dict:
        """
        Determines routing information for an incoming call based on the DID.

        Args:
            did_number (str): The dialed number (DID).

        Returns:
            dict: A dictionary containing either:
                  {'status': 'proceed', 'routing_info': { ... }}
                  or
                  {'status': 'reject', 'reject_reason': 'reason_code'}
        """
        logger.info(f"Routing request received for DID: {did_number}")

        # 1. Find the DID and its owner (User)
        # Eager load owner to potentially check user status later if needed
        did_record = DidModel.query.options(joinedload(DidModel.owner))\
                           .filter(DidModel.number == did_number)\
                           .one_or_none()

        if not did_record:
            logger.warning(f"DID not found: {did_number}")
            return {"status": "reject", "reject_reason": "did_not_found"}

        if did_record.status != 'active':
            logger.warning(f"DID {did_number} is inactive.")
            return {"status": "reject", "reject_reason": "did_inactive"}

        if not did_record.owner or did_record.owner.status != 'active':
             logger.warning(f"Owner (User ID: {did_record.user_id}) of DID {did_number} is inactive or missing.")
             return {"status": "reject", "reject_reason": "owner_inactive"}

        user_id = did_record.user_id
        did_id = did_record.id
        logger.debug(f"DID {did_number} (ID: {did_id}) found, owned by User ID: {user_id}")

        # 2. Find the Active Campaign linked to this DID for this User
        # Subquery to find campaign IDs linked to the DID
        campaign_link = db.session.query(CampaignDidModel.campaign_id)\
                             .filter(CampaignDidModel.did_id == did_id)\
                             .subquery()

        # Query the Campaign, filtering by active status and link existence
        active_campaign = CampaignModel.query.filter(
            CampaignModel.user_id == user_id,
            CampaignModel.status == 'active',
            CampaignModel.id.in_(select(campaign_link))
        ).first() # Assuming one active campaign per DID, could adjust if multiple needed

        if not active_campaign:
            logger.warning(f"No active campaign found linked to DID ID {did_id} for User ID {user_id}.")
            return {"status": "reject", "reject_reason": "no_active_campaign_for_did"}

        campaign_id = active_campaign.id
        routing_strategy = active_campaign.routing_strategy
        dial_timeout_seconds = active_campaign.dial_timeout_seconds
        logger.debug(f"Active Campaign ID: {campaign_id}, Strategy: {routing_strategy}, Timeout: {dial_timeout_seconds}s")

        # 3. Find eligible Client Settings for this Campaign
        # Query CampaignClientSettings, joining related tables needed for filtering and response data
        query = CampaignClientSettingsModel.query.options(
                    joinedload(CampaignClientSettingsModel.client).options(
                        # Eager load PJSIP info needed for routing
                        joinedload(ClientModel.pjsip_endpoint),
                        joinedload(ClientModel.pjsip_aor)
                    )
                ).filter(
                    CampaignClientSettingsModel.campaign_id == campaign_id,
                    CampaignClientSettingsModel.status == 'active'
                ).join(ClientModel).filter(
                    ClientModel.status == 'active'
                ).join(PjsipEndpointModel).join(PjsipAorModel) # Ensure PJSIP records exist


        # Apply ordering based on strategy
        if routing_strategy == 'priority':
            query = query.order_by(CampaignClientSettingsModel.forwarding_priority.asc())
        elif routing_strategy == 'round_robin':
            # Simple round-robin might need external state or more complex DB query (e.g., using modulo or random)
            # For now, just order by ID for deterministic pseudo-RR, actual RR state handled by Asterisk logic potentially
            logger.warning("Simple ID ordering used for 'round_robin'. Consider stateful logic if true RR needed.")
            query = query.order_by(CampaignClientSettingsModel.id.asc())
        elif routing_strategy == 'weighted':
            # Weighted selection typically happens *after* fetching eligible candidates.
            # Order by priority first (if weights are equal), then fetch all to select based on weight.
             logger.warning("Ordering by priority/ID for 'weighted'. Selection logic applied after fetching.")
             query = query.order_by(CampaignClientSettingsModel.forwarding_priority.asc(), CampaignClientSettingsModel.id.asc())
        else: # Default to priority
             query = query.order_by(CampaignClientSettingsModel.forwarding_priority.asc())

        potential_targets_settings = query.all()

        if not potential_targets_settings:
            logger.warning(f"No active clients linked or configured properly (PJSIP missing?) for Campaign ID {campaign_id}.")
            return {"status": "reject", "reject_reason": "no_active_clients_in_campaign"}

        # 4. Filter Targets by Total Cap and Format Response
        eligible_targets_list = []
        for setting in potential_targets_settings:
            client = setting.client
            endpoint = client.pjsip_endpoint
            aor = client.pjsip_aor

            if not endpoint or not aor or not aor.contact:
                logger.warning(f"Skipping Client ID {client.id} for Campaign {campaign_id} due to missing/incomplete PJSIP Endpoint/AOR/Contact config.")
                continue

            # Check total calls cap
            total_allowed = setting.total_calls_allowed
            if total_allowed is not None and setting.current_total_calls >= total_allowed:
                logger.info(f"Skipping Client ID {client.id} (Setting ID: {setting.id}) for Campaign {campaign_id}: Total cap ({total_allowed}) reached (Current: {setting.current_total_calls}).")
                continue # Skip this client

            # Add to eligible list if passes checks
            eligible_targets_list.append({
                "ccs_id": setting.id, # CampaignClientSetting ID (useful for logging)
                "client_id": client.id,
                "client_identifier": client.client_identifier, # Used for PJSIP Endpoint ID / GROUP name
                "client_name": client.name, # For logging/info
                "sip_uri": aor.contact, # The actual destination URI(s)
                "max_concurrency": setting.max_concurrency, # Specific CC for this link
                "weight": setting.weight, # For weighted routing logic in Asterisk
                "priority": setting.forwarding_priority, # For info/ordering
                # Include optional PJSIP details if needed by Asterisk dialplan
                "outbound_auth": endpoint.outbound_auth if endpoint else None,
                "callerid_override": endpoint.callerid if endpoint else None,
                "context": endpoint.context if endpoint else None, # Context where the call might land on client side (less common for sending)
                "transport": endpoint.transport if endpoint else None
            })

        # 5. Handle Weighted Distribution Selection (if applicable)
        # Note: True weighted requires selecting ONE target based on weights.
        # This example returns ALL eligible targets ordered, Asterisk dialplan
        # would need to implement the weighted selection logic itself, or
        # this service could be enhanced to pick one based on weights.
        # For now, we return the ordered list.

        if not eligible_targets_list:
            logger.warning(f"No eligible clients found for Campaign ID {campaign_id} after filtering (e.g., all capped).")
            return {"status": "reject", "reject_reason": "no_eligible_clients_available"}

        # 6. Prepare final response
        routing_info = {
            "user_id": user_id,
            "campaign_id": campaign_id,
            "routing_strategy": routing_strategy,
            "dial_timeout_seconds": dial_timeout_seconds,
            "targets": eligible_targets_list # List of eligible targets, ordered
        }

        logger.info(f"Routing info found for DID {did_number}. Strategy: {routing_strategy}. Eligible Targets: {len(eligible_targets_list)}")
        return {"status": "proceed", "routing_info": routing_info}