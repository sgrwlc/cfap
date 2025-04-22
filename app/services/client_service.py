# -*- coding: utf-8 -*-
"""
Client Service
Handles business logic for managing Clients (Call Centers) and their
associated PJSIP configurations required for Asterisk ARA.
"""
from sqlalchemy import select, delete, and_ # Import and_
from sqlalchemy.exc import IntegrityError
from flask import current_app # Import current_app for logging
from flask_sqlalchemy.pagination import Pagination
from sqlalchemy.orm import joinedload
from app.database.models.client import ClientModel
from app.database.models.pjsip import PjsipEndpointModel, PjsipAorModel, PjsipAuthModel
# --- Added imports needed for the check ---
from app.database.models.campaign import CampaignModel, CampaignClientSettingsModel
# --- End added imports ---
from app.extensions import db
# from app.utils.exceptions import NotFoundError, ConflictError, ServiceError # Example custom exceptions

class ClientService:

    @staticmethod
    def create_client_with_pjsip(creator_user_id: int, client_data: dict, pjsip_data: dict):
        """
        Creates a new Client and its associated PJSIP configuration records atomically.

        Args:
            creator_user_id (int): The ID of the admin/staff user creating the client.
            client_data (dict): Dictionary containing ClientModel fields
                                (client_identifier, name, department, status, notes).
            pjsip_data (dict): Dictionary containing PJSIP config fields:
                                {
                                    "endpoint": {id, transport, aors, context, allow, ...},
                                    "aor": {id, contact, max_contacts, ...},
                                    "auth": {id, auth_type, username, password, realm} (optional)
                                }

        Returns:
            ClientModel: The newly created client instance with associated PJSIP data populated.

        Raises:
            ValueError: If required data is missing, invalid, or conflicts exist.
            # Consider custom exceptions like ConflictError, ServiceError later
        """
        client_identifier = client_data.get('client_identifier')
        if not client_identifier:
            raise ValueError("Client identifier is required.")

        # Basic check for pjsip data structure
        endpoint_config = pjsip_data.get('endpoint')
        aor_config = pjsip_data.get('aor')
        auth_config = pjsip_data.get('auth') # Optional

        if not endpoint_config or not aor_config:
            raise ValueError("PJSIP endpoint and AOR configuration data are required.")
        if endpoint_config.get('id') != client_identifier or aor_config.get('id') != client_identifier:
             raise ValueError("PJSIP endpoint ID and AOR ID must match the client_identifier.")
        if auth_config and auth_config.get('id') is None:
             raise ValueError("PJSIP auth ID is required if auth section is provided.")
        # Add more validation for required fields within pjsip configs (e.g., aor.contact)


        # Check for existing identifier
        if ClientModel.query.filter_by(client_identifier=client_identifier).first():
            raise ValueError(f"Client identifier '{client_identifier}' already exists.")
            # raise ConflictError(f"Client identifier '{client_identifier}' already exists.")


        session = db.session
        try:
            # 1. Create Client
            new_client = ClientModel(
                created_by=creator_user_id,
                **client_data
            )
            session.add(new_client)
            # Flush to get the new_client.id if needed, but wait to commit
            session.flush()

            # 2. Create PJSIP Endpoint
            new_endpoint = PjsipEndpointModel(
                client_id=new_client.id,
                **endpoint_config
            )
            session.add(new_endpoint)

            # 3. Create PJSIP AOR
            new_aor = PjsipAorModel(
                client_id=new_client.id,
                **aor_config
            )
            session.add(new_aor)

            # 4. Create PJSIP Auth (if provided)
            if auth_config:
                new_auth = PjsipAuthModel(
                    client_id=new_client.id,
                    **auth_config
                )
                session.add(new_auth)

            # Commit all changes together
            session.commit()
            return new_client

        except IntegrityError as e:
            session.rollback()
            # Log the error e
            # Check if it's specifically the unique constraint
            if 'unique constraint' in str(e.orig).lower() and 'client_identifier' in str(e.orig).lower():
                 raise ValueError(f"Client identifier '{client_identifier}' already exists.")
            elif 'unique constraint' in str(e.orig).lower() and 'pjsip_' in str(e.orig).lower():
                 raise ValueError(f"PJSIP configuration ID conflict for '{client_identifier}'. Check endpoint, AOR, or auth IDs.")
            else:
                 raise ValueError("Database integrity error during client creation.")
        except Exception as e:
            session.rollback()
            # Log the error e
            raise ValueError(f"Failed to create client due to an unexpected error: {e}")
            # raise ServiceError(f"Failed to create client: {e}")

    @staticmethod
    def get_client_by_id(client_id: int) -> ClientModel | None:
        """Fetches a client by its primary key ID."""
        # Use options to load related PJSIP data eagerly if often needed together
        # from sqlalchemy.orm import joinedload
        # return ClientModel.query.options(joinedload('*')).get(client_id)
        return db.session.get(ClientModel, client_id)

    @staticmethod
    def get_client_by_identifier(identifier: str) -> ClientModel | None:
        """Fetches a client by its unique client_identifier string."""
        return ClientModel.query.filter_by(client_identifier=identifier).one_or_none()

    @staticmethod
    def get_all_clients(page: int = 1, per_page: int = 20, status: str | None = None) -> Pagination:
        """
        Fetches a paginated list of clients, optionally filtered by status.

        Args:
            page (int): Page number.
            per_page (int): Items per page.
            status (str, optional): Filter by status ('active' or 'inactive').

        Returns:
            Pagination: Flask-SQLAlchemy Pagination object.
        """
        query = ClientModel.query.order_by(ClientModel.name)
        if status and status in ['active', 'inactive']:
            query = query.filter(ClientModel.status == status)

        clients = query.paginate(page=page, per_page=per_page, error_out=False)
        return clients

    @staticmethod
    def update_client_with_pjsip(client_id: int, client_data: dict, pjsip_data: dict):
        """
        Updates a Client and its associated PJSIP configuration records atomically.

        Args:
            client_id (int): The ID of the client to update.
            client_data (dict): Dictionary containing ClientModel fields to update.
                                Cannot update client_identifier here.
            pjsip_data (dict): Dictionary containing PJSIP fields to update:
                                { "endpoint": {...}, "aor": {...}, "auth": {...} }
                                Auth section is created if not existing and provided,
                                updated if existing, or deleted if set to None.

        Returns:
            ClientModel: The updated client instance.

        Raises:
            ValueError: If client not found, data invalid, or update fails.
            # Consider NotFoundError, ServiceError
        """
        client = ClientService.get_client_by_id(client_id)
        if not client:
            raise ValueError(f"Client with ID {client_id} not found.")
            # raise NotFoundError(f"Client with ID {client_id} not found.")

        # Prevent identifier change via this method
        if 'client_identifier' in client_data and client_data['client_identifier'] != client.client_identifier:
             raise ValueError("Client identifier cannot be changed.")

        # Basic check for pjsip data structure
        endpoint_config = pjsip_data.get('endpoint', {}) # Use empty dict if not provided
        aor_config = pjsip_data.get('aor', {})
        auth_config = pjsip_data.get('auth') # Can be None to signal deletion


        session = db.session
        try:
            # 1. Update Client fields
            allowed_client_updates = ['name', 'department', 'status', 'notes']
            client_updated = False
            for key, value in client_data.items():
                if key in allowed_client_updates:
                    setattr(client, key, value)
                    client_updated = True

            # 2. Update PJSIP Endpoint
            endpoint_updated = False
            if client.pjsip_endpoint and endpoint_config:
                for key, value in endpoint_config.items():
                     if key != 'id' and key != 'client_id': # Prevent changing PK/FK
                          setattr(client.pjsip_endpoint, key, value)
                          endpoint_updated = True
            elif endpoint_config: # Should not happen if client exists unless DB inconsistent
                 raise ValueError("PJSIP Endpoint record missing for existing client.")


            # 3. Update PJSIP AOR
            aor_updated = False
            if client.pjsip_aor and aor_config:
                for key, value in aor_config.items():
                     if key != 'id' and key != 'client_id':
                          setattr(client.pjsip_aor, key, value)
                          aor_updated = True
            elif aor_config:
                  raise ValueError("PJSIP AOR record missing for existing client.")

            # 4. Update/Create/Delete PJSIP Auth
            auth_updated = False
            if auth_config is None: # Signal to delete auth if it exists
                 if client.pjsip_auth:
                      session.delete(client.pjsip_auth)
                      auth_updated = True
            elif isinstance(auth_config, dict):
                 if client.pjsip_auth: # Update existing auth
                      auth_id = auth_config.get('id')
                      if auth_id and auth_id != client.pjsip_auth.id:
                           raise ValueError("Cannot change existing PJSIP Auth ID.")
                      for key, value in auth_config.items():
                          if key != 'id' and key != 'client_id':
                               setattr(client.pjsip_auth, key, value)
                               auth_updated = True
                 else: # Create new auth
                      auth_id = auth_config.get('id')
                      if not auth_id:
                          raise ValueError("PJSIP Auth ID is required to create new auth.")
                      new_auth = PjsipAuthModel(
                          id=auth_id, # Use provided ID
                          client_id=client.id,
                          **{k: v for k, v in auth_config.items() if k != 'id'}
                      )
                      session.add(new_auth)
                      auth_updated = True

            # Commit if any changes were made
            if client_updated or endpoint_updated or aor_updated or auth_updated:
                session.commit()
            return client

        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to update client due to an unexpected error: {e}")
            # raise ServiceError(f"Failed to update client: {e}")

    @staticmethod
    def delete_client(client_id: int) -> bool:
        """
        Deletes a client and its associated PJSIP records (via cascade).
        Prevents deletion if the client is linked via an active setting
        to an active campaign. Includes DEBUGGING logic using print().

        Args:
            client_id (int): The ID of the client to delete.

        Returns:
            bool: True if deletion was successful (always returns True or raises).

        Raises:
            ValueError: If client not found, linked to active campaign, or DB error during commit.
        """
        client = db.session.get(ClientModel, client_id)
        if not client:
            raise ValueError(f"Client with ID {client_id} not found.")

        # --- DEBUGGING LOGS using print() ---
        print(f"\nDEBUG: Attempting delete for Client ID: {client_id} (Identifier: {client.client_identifier})")

        # Check related CampaignClientSettings
        settings_links = []
        try:
            settings_links = db.session.query(CampaignClientSettingsModel).filter(
                CampaignClientSettingsModel.client_id == client_id
            ).options(
                # Eager load campaign for status check below
                joinedload(CampaignClientSettingsModel.campaign)
            ).all()
        except Exception as e:
            # Use print for exception here too during debugging
            import traceback
            print(f"\nDEBUG: Error querying CampaignClientSettings links for Client ID {client_id}: {e}")
            traceback.print_exc() # Print full traceback
            raise ValueError(f"Could not verify campaign links before deleting client {client_id}.")

        print(f"\nDEBUG: Found {len(settings_links)} CampaignClientSettings links for Client ID {client_id}.")
        link_is_active_to_active_campaign = False # Flag to track if blocking condition met

        for link in settings_links:
             campaign = link.campaign # Access eager-loaded campaign
             campaign_status = getattr(campaign, 'status', 'N/A')
             print(
                 f"DEBUG:   - Link ID: {link.id}, Link Status: {link.status}, "
                 f"Campaign ID: {link.campaign_id}, Campaign Status: {campaign_status}"
             )
             # Check the actual condition we care about
             if link.status == 'active' and campaign_status == 'active':
                 link_is_active_to_active_campaign = True
                 print(f"DEBUG:   ^^^ Blocking condition met by Link ID {link.id}")


        # Optional: Log the result of the intended complex check
        try:
            q_complex = db.session.query(CampaignClientSettingsModel.id)\
                .join(CampaignModel, CampaignClientSettingsModel.campaign_id == CampaignModel.id)\
                .filter(CampaignClientSettingsModel.client_id == client_id)\
                .filter(CampaignClientSettingsModel.status == 'active')\
                .filter(CampaignModel.status == 'active')\
                .exists()
            complex_check_result = db.session.query(q_complex).scalar()
            print(f"\nDEBUG: Result of COMPLEX check query for active/active link: {complex_check_result}")
        except Exception as e:
            print(f"\nDEBUG: Error running complex check query: {e}")


        # Use the flag set during iteration for blocking deletion
        if link_is_active_to_active_campaign:
             # Optional: Log the specific campaign IDs if helpful for debugging
             try:
                 linked_campaign_ids = [link.campaign_id for link in settings_links if link.status == 'active' and getattr(link.campaign, 'status', 'N/A') == 'active']
                 ids_str = ', '.join(map(str, linked_campaign_ids))
                 msg = f"Cannot delete client {client_id}. It is actively linked to active campaigns (IDs: [{ids_str}]). Deactivate campaigns or links first."
                 print(f"\nDEBUG: Preventing deletion of Client ID {client_id}. Linked via active settings to active Campaign IDs: [{ids_str}]")
             except Exception: # Fallback if constructing message fails
                  msg = f"Cannot delete client {client_id} because it is linked to active campaigns. Deactivate links first."
                  print(f"\nDEBUG: Preventing deletion of Client ID {client_id}. Linked via active settings to active Campaign(s).")
             raise ValueError(msg)
        # --- END DEBUGGING ---


        # Proceed with deletion if checks pass
        print(f"\nDEBUG: Proceeding with deletion for Client ID: {client_id} as no active links to active campaigns were found.")
        session = db.session # Use alias for clarity
        try:
            session.delete(client)
            session.commit() # Try to commit
            print(f"\nDEBUG: Successfully committed deletion of Client ID {client_id}.")
            return True # Return True ONLY after successful commit
        except Exception as e:
            session.rollback() # Rollback on ANY exception during delete/commit
            # Use print for exception here too during debugging
            import traceback
            print(f"\nDEBUG: Database error during deletion commit for Client ID {client_id}: {e}")
            traceback.print_exc() # Print full traceback
            # Re-raise as a ValueError or a more specific custom Exception
            raise ValueError(f"Failed to commit client deletion due to database error.")