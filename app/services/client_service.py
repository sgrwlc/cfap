# app/services/client_service.py
# -*- coding: utf-8 -*-
"""
Client Service
Handles business logic for managing Clients (Call Centers) and their associated
PJSIP configurations required for Asterisk ARA.
Service methods modify the session but DO NOT COMMIT.
"""
from sqlalchemy import select, delete, and_ # Import and_
from sqlalchemy.exc import IntegrityError
from flask import current_app # Import current_app for logging
from flask_sqlalchemy.pagination import Pagination
from sqlalchemy.orm import joinedload, Session # Added Session for typing

from app.database.models.client import ClientModel
from app.database.models.pjsip import PjsipEndpointModel, PjsipAorModel, PjsipAuthModel
from app.database.models.campaign import CampaignModel, CampaignClientSettingsModel
from app.extensions import db
# Import custom exceptions
from app.utils.exceptions import ResourceNotFound, ConflictError, ServiceError, ValidationError, AuthorizationError


class ClientService:

    @staticmethod
    def create_client_with_pjsip(creator_user_id: int, client_data: dict, pjsip_data: dict) -> ClientModel:
        """
        Creates a new Client and its associated PJSIP configuration records.
        Adds objects to the session but DOES NOT COMMIT.

        Args:
            creator_user_id (int): The ID of the admin/staff user creating the client.
            client_data (dict): ClientModel fields (client_identifier, name, etc.).
            pjsip_data (dict): PJSIP config: {"endpoint":{...}, "aor":{...}, "auth":{...} (optional)}

        Returns:
            ClientModel: The newly created client instance, added to the session.

        Raises:
            ValidationError: If required data is missing or invalid (e.g., mismatched IDs).
            ConflictError: If client_identifier or PJSIP IDs conflict with existing records.
            ServiceError: For database integrity errors or unexpected errors during flush.
        """
        client_identifier = client_data.get('client_identifier')
        if not client_identifier:
            raise ValidationError("Client identifier is required.")

        endpoint_config = pjsip_data.get('endpoint')
        aor_config = pjsip_data.get('aor')
        auth_config = pjsip_data.get('auth') # Optional

        # Validate required PJSIP sections and IDs
        if not endpoint_config or not aor_config:
            raise ValidationError("PJSIP endpoint and AOR configuration data are required.")
        if endpoint_config.get('id') != client_identifier:
             raise ValidationError("PJSIP endpoint ID must match the client_identifier.")
        if aor_config.get('id') != client_identifier:
             raise ValidationError("PJSIP AOR ID must match the client_identifier.")
        if auth_config and not auth_config.get('id'):
             raise ValidationError("PJSIP auth ID is required if auth section is provided.")
        # Add more specific PJSIP field validation if needed (e.g., aor.contact)
        if not aor_config.get('contact'):
             raise ValidationError("PJSIP AOR contact field is required.")
        if not endpoint_config.get('context'):
             raise ValidationError("PJSIP Endpoint context field is required.")

        # Check for existing identifier within the current transaction context
        if db.session.query(ClientModel.id).filter_by(client_identifier=client_identifier).first():
            raise ConflictError(f"Client identifier '{client_identifier}' already exists.")
        # Check PJSIP ID conflicts (less likely if tied to client_id FK, but check primary keys)
        if db.session.query(PjsipEndpointModel.id).filter_by(id=client_identifier).first():
            raise ConflictError(f"PJSIP Endpoint ID '{client_identifier}' already exists.")
        if db.session.query(PjsipAorModel.id).filter_by(id=client_identifier).first():
             raise ConflictError(f"PJSIP AOR ID '{client_identifier}' already exists.")
        if auth_config and db.session.query(PjsipAuthModel.id).filter_by(id=auth_config['id']).first():
             raise ConflictError(f"PJSIP Auth ID '{auth_config['id']}' already exists.")


        session = db.session # Use alias for clarity
        try:
            # 1. Create Client
            new_client = ClientModel(
                created_by=creator_user_id,
                **client_data
            )
            session.add(new_client)
            session.flush() # Flush early to get client ID and check constraints

            # 2. Create PJSIP Endpoint
            new_endpoint = PjsipEndpointModel(
                client_id=new_client.id, # Link to the newly created client
                **endpoint_config
            )
            session.add(new_endpoint)

            # 3. Create PJSIP AOR
            new_aor = PjsipAorModel(
                client_id=new_client.id, # Link to the newly created client
                **aor_config
            )
            session.add(new_aor)

            # 4. Create PJSIP Auth (if provided)
            if auth_config:
                new_auth = PjsipAuthModel(
                    client_id=new_client.id, # Link to the newly created client
                    **auth_config
                )
                session.add(new_auth)

            session.flush() # Final flush to check all PJSIP constraints
            current_app.logger.info(f"Client '{client_identifier}' and PJSIP config added to session.")
            # DO NOT COMMIT HERE - Handled by the route
            return new_client

        except IntegrityError as e:
            session.rollback()
            current_app.logger.error(f"Database integrity error creating client '{client_identifier}': {e}", exc_info=True)
            # More specific error checking based on constraint name if possible
            if 'unique constraint' in str(e.orig).lower():
                 # Could be client_identifier or pjsip IDs if initial checks missed a race condition
                 raise ConflictError(f"Conflict during client creation (check identifier/PJSIP IDs): {e.orig}")
            elif 'foreign key constraint' in str(e.orig).lower():
                 raise ServiceError(f"Data integrity error creating client (check creator user ID?): {e.orig}")
            else:
                 raise ServiceError(f"Database integrity error during client creation: {e.orig}")
        except Exception as e:
            session.rollback()
            current_app.logger.error(f"Unexpected error creating client '{client_identifier}': {e}", exc_info=True)
            raise ServiceError(f"Failed to create client: {e}")

    @staticmethod
    def get_client_by_id(client_id: int) -> ClientModel | None:
        """Fetches a client by its primary key ID, eagerly loading PJSIP info."""
        # Eagerly load PJSIP relations as they are often needed together
        load_options = [
            joinedload(ClientModel.pjsip_endpoint),
            joinedload(ClientModel.pjsip_aor),
            joinedload(ClientModel.pjsip_auth)
        ]
        return db.session.get(ClientModel, client_id, options=load_options)

    @staticmethod
    def get_client_by_identifier(identifier: str) -> ClientModel | None:
        """Fetches a client by its unique client_identifier string."""
        return db.session.query(ClientModel).filter_by(client_identifier=identifier).one_or_none()

    @staticmethod
    def get_all_clients(page: int = 1, per_page: int = 20, status: str | None = None) -> Pagination:
        """Fetches a paginated list of clients, optionally filtered by status."""
        query = db.session.query(ClientModel).order_by(ClientModel.name)
        if status and status in ['active', 'inactive']:
            query = query.filter(ClientModel.status == status)
        # Schema should validate status value

        # Eager load PJSIP data for the list view as well if the schema includes it
        query = query.options(
             joinedload(ClientModel.pjsip_endpoint),
             joinedload(ClientModel.pjsip_aor),
             joinedload(ClientModel.pjsip_auth)
        )

        pagination = query.paginate(page=page, per_page=per_page, error_out=False, count=True)
        return pagination

    @staticmethod
    def update_client_with_pjsip(client_id: int, client_data: dict, pjsip_data: dict) -> ClientModel:
        """
        Updates a Client and its associated PJSIP configuration records in the session.
        DOES NOT COMMIT.

        Args:
            client_id (int): The ID of the client to update.
            client_data (dict): ClientModel fields to update (cannot update client_identifier).
            pjsip_data (dict): PJSIP fields to update: {"endpoint":{...}, "aor":{...}, "auth":{.../None}}.
                               Auth set to None deletes the auth record.

        Returns:
            ClientModel: The updated client instance present in the session.

        Raises:
            ResourceNotFound: If client not found.
            ValidationError: If data is invalid (e.g., trying to change identifier, invalid PJSIP data).
            ConflictError: If a PJSIP ID conflict occurs (e.g., changing auth ID to an existing one).
            ServiceError: For unexpected errors during update/flush.
        """
        client = ClientService.get_client_by_id(client_id)
        if not client:
            raise ResourceNotFound(f"Client with ID {client_id} not found.")

        if 'client_identifier' in client_data and client_data['client_identifier'] != client.client_identifier:
             raise ValidationError("Client identifier cannot be changed.")

        session = db.session
        updated = False
        pjsip_updated = False # Track pjsip changes specifically

        endpoint_config = pjsip_data.get('endpoint', {})
        aor_config = pjsip_data.get('aor', {})
        auth_config = pjsip_data.get('auth') # Can be None or dict

        try:
            # 1. Update Client fields
            allowed_client_updates = ['name', 'department', 'status', 'notes']
            for key, value in client_data.items():
                if key in allowed_client_updates:
                     # Schema should validate status enum
                     setattr(client, key, value)
                     updated = True

            # --- PJSIP Updates ---
            # 2. Update PJSIP Endpoint
            if not client.pjsip_endpoint:
                 raise ServiceError(f"Inconsistent state: PJSIP Endpoint missing for Client ID {client_id}.")
            if endpoint_config:
                 for key, value in endpoint_config.items():
                      if key != 'id' and key != 'client_id': # Prevent changing PK/FK
                           if getattr(client.pjsip_endpoint, key) != value:
                                setattr(client.pjsip_endpoint, key, value)
                                pjsip_updated = True

            # 3. Update PJSIP AOR
            if not client.pjsip_aor:
                raise ServiceError(f"Inconsistent state: PJSIP AOR missing for Client ID {client_id}.")
            if aor_config:
                for key, value in aor_config.items():
                     if key != 'id' and key != 'client_id':
                          if getattr(client.pjsip_aor, key) != value:
                               setattr(client.pjsip_aor, key, value)
                               pjsip_updated = True

            # 4. Update/Create/Delete PJSIP Auth
            auth_id_being_processed = None # Track ID for potential deletion/reference clearing
            if client.pjsip_auth:
                auth_id_being_processed = client.pjsip_auth.id # Get ID of existing auth

            if auth_config is None: # Signal to delete auth
                 if client.pjsip_auth:
                      auth_id_to_delete = client.pjsip_auth.id # Capture ID before deleting
                      current_app.logger.debug(f"Deleting PJSIP Auth ID '{auth_id_to_delete}' for Client {client_id}.")
                      session.delete(client.pjsip_auth)
                      client.pjsip_auth = None # Clear relation on client object

                      # Correctly clear references on the endpoint *using the captured ID*
                      if client.pjsip_endpoint:
                          if client.pjsip_endpoint.auth == auth_id_to_delete:
                              client.pjsip_endpoint.auth = None
                              current_app.logger.debug(f"Cleared endpoint.auth reference to '{auth_id_to_delete}'.")
                              pjsip_updated = True # Mark endpoint as updated
                          if client.pjsip_endpoint.outbound_auth == auth_id_to_delete:
                              client.pjsip_endpoint.outbound_auth = None
                              current_app.logger.debug(f"Cleared endpoint.outbound_auth reference to '{auth_id_to_delete}'.")
                              pjsip_updated = True # Mark endpoint as updated

                      # pjsip_updated = True # Already marked if refs cleared
            elif isinstance(auth_config, dict):
                 auth_id = auth_config.get('id')
                 if not auth_id:
                      raise ValidationError("PJSIP Auth ID is required when providing auth data.")

                 if client.pjsip_auth: # Update existing auth
                      if auth_id != client.pjsip_auth.id:
                           raise ValidationError("Cannot change existing PJSIP Auth ID via update.")
                      for key, value in auth_config.items():
                           if key != 'id' and key != 'client_id':
                                if getattr(client.pjsip_auth, key) != value:
                                     setattr(client.pjsip_auth, key, value)
                                     pjsip_updated = True
                 else: # Create new auth
                      if db.session.query(PjsipAuthModel.id).filter_by(id=auth_id).first():
                           raise ConflictError(f"PJSIP Auth ID '{auth_id}' already exists.")
                      current_app.logger.debug(f"Creating new PJSIP Auth ID '{auth_id}' for Client {client_id}.")
                      new_auth = PjsipAuthModel(
                          id=auth_id,
                          client_id=client.id,
                          **{k: v for k, v in auth_config.items() if k != 'id'}
                      )
                      session.add(new_auth)
                      client.pjsip_auth = new_auth
                      pjsip_updated = True

            # --- Final Flush ---
            if updated or pjsip_updated:
                session.flush() # Flush to check all constraints
                current_app.logger.info(f"Client ID {client_id} and/or PJSIP config updated in session.")
            else:
                 current_app.logger.info(f"No valid fields provided to update Client ID {client_id}.")

            # DO NOT COMMIT HERE - Handled by the route
            return client

        except IntegrityError as e:
            session.rollback()
            current_app.logger.error(f"Database integrity error updating client {client_id}: {e}", exc_info=True)
            if 'unique constraint "pjsip_auths_pkey"' in str(e.orig).lower() or \
               'unique constraint "pjsip_auths_client_id_key"' in str(e.orig).lower():
                 raise ConflictError(f"PJSIP Auth ID conflict: {e.orig}")
            # Add checks for other constraints if needed (e.g., pjsip_endpoints_pkey)
            elif 'unique constraint "pjsip_endpoints_pkey"' in str(e.orig).lower() or \
                 'unique constraint "pjsip_aors_pkey"' in str(e.orig).lower():
                 # Should not happen if ID isn't changeable, but catch just in case
                 raise ConflictError(f"PJSIP Endpoint/AOR ID conflict: {e.orig}")
            raise ServiceError(f"Database integrity error during client update: {e.orig}")
        except Exception as e:
            session.rollback()
            current_app.logger.error(f"Unexpected error updating client {client_id}: {e}", exc_info=True)
            raise ServiceError(f"Failed to update client: {e}")


    @staticmethod
    def delete_client(client_id: int) -> bool:
        """
        Marks a client for deletion in the session (DOES NOT COMMIT).
        Associated PJSIP records are handled by cascade delete in the DB relationship.
        Prevents deletion if the client is linked via an active setting to an active campaign.

        Args:
            client_id (int): The ID of the client to delete.

        Returns:
            bool: True if the client was marked for deletion in the session.

        Raises:
            ResourceNotFound: If client not found.
            ConflictError: If client is linked to active campaigns.
            ServiceError: For unexpected errors during delete/flush or consistency checks.
        """
        client = db.session.get(ClientModel, client_id)
        if not client:
            raise ResourceNotFound(f"Client with ID {client_id} not found.")

        # Check if this client is part of any ACTIVE setting linked to an ACTIVE campaign
        try:
            is_linked_to_active = db.session.query(CampaignClientSettingsModel.id)\
                .join(CampaignModel, CampaignClientSettingsModel.campaign_id == CampaignModel.id)\
                .filter(CampaignClientSettingsModel.client_id == client_id)\
                .filter(CampaignClientSettingsModel.status == 'active')\
                .filter(CampaignModel.status == 'active')\
                .limit(1).scalar() is not None # Use limit(1).scalar() for efficiency

            if is_linked_to_active:
                current_app.logger.warning(f"Attempt to delete client {client_id} failed: Linked to active campaign(s).")
                # Consider querying the specific campaign names/IDs for a more informative message if needed
                raise ConflictError(f"Cannot delete client {client_id}. It is actively linked to one or more active campaigns. Deactivate the campaigns or the links first.")
        # --- Catch the specific ConflictError FIRST ---
        except ConflictError as e:
            # Re-raise it immediately for the route to handle
            raise e
        # --- Catch other potential errors during the check ---
        except Exception as e:
            # Handle potential errors during the check itself
            current_app.logger.error(f"Error checking active campaign links for client {client_id}: {e}", exc_info=True)
            # Reraise as ServiceError as this check is internal prerequisite
            raise ServiceError("Could not verify campaign links before deleting client.")



        # Proceed with marking for deletion if checks pass
        session = db.session # Alias for clarity
        try:
            # Deleting the client will cascade delete related PJSIP records and CampaignClientSettings due to relationship settings
            session.delete(client)
            session.flush() # Flush to potentially catch FK issues early if cascade isn't configured perfectly
            current_app.logger.info(f"Client ID {client_id} marked for deletion in session.")
            return True
            # DO NOT COMMIT HERE - Handled by the route
        # except IntegrityError as e: # Catch integrity errors on flush (e.g., FK constraints if cascade fails)
        #     session.rollback()
        #     current_app.logger.error(f"Database integrity error deleting client {client_id}: {e}", exc_info=True)
        #     raise ServiceError(f"Failed to stage client deletion due to DB constraints: {e.orig}")
        except Exception as e:
            session.rollback()
            current_app.logger.error(f"Unexpected error deleting client {client_id}: {e}", exc_info=True)
            # Re-raise as a ServiceError
            raise ServiceError(f"Failed to stage client deletion: {e}")