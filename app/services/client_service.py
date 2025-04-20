# -*- coding: utf-8 -*-
"""
Client Service
Handles business logic for managing Clients (Call Centers) and their
associated PJSIP configurations required for Asterisk ARA.
"""
from sqlalchemy.exc import IntegrityError
# --- MODIFICATION: Import select, exists, and_ ---
from sqlalchemy import select, exists, and_
# --- MODIFICATION: Import Pagination ---
from flask_sqlalchemy.pagination import Pagination

from app.database.models.client import ClientModel
# --- MODIFICATION: Import CampaignClientSettingsModel directly for the exists query ---
from app.database.models.campaign import CampaignClientSettingsModel
from app.database.models.pjsip import PjsipEndpointModel, PjsipAorModel, PjsipAuthModel
from app.extensions import db
# from app.utils.exceptions import NotFoundError, ConflictError, ServiceError # Example custom exceptions
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
        return ClientModel.query.get(client_id)

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

        Args:
            client_id (int): The ID of the client to delete.

        Returns:
            bool: True if deletion was successful.

        Raises:
            ValueError: If client not found or deletion fails.
            # Consider NotFoundError, ServiceError
        """
        client = ClientService.get_client_by_id(client_id)
        if not client:
            raise ValueError(f"Client with ID {client_id} not found.")
            # raise NotFoundError(f"Client with ID {client_id} not found.")

        # Add checks here? e.g., prevent deletion if linked to active campaign_client_settings?
        active_links = db.session.query(db.exists().where(
            db.and_(
                CampaignClientSettingsModel.client_id == client_id,
                CampaignClientSettingsModel.status == 'active'
            )
        )).scalar()

        if active_links:
            raise ValueError(f"Cannot delete client {client_id} because it is linked to active campaigns. Deactivate links first.")
            # raise ConflictError(...)

        session = db.session
        try:
            # Deleting the client will cascade delete related PJSIP records
            # due to `cascade="all, delete-orphan"` and `ondelete='CASCADE'` in models
            session.delete(client)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            # Log error e
            raise ValueError(f"Failed to delete client due to an unexpected error: {e}")
            # raise ServiceError(f"Failed to delete client: {e}")