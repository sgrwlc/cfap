# app/database/models/pjsip.py
# -*- coding: utf-8 -*-
"""
PJSIP Configuration models for Asterisk Realtime Architecture (ARA).

These models map directly to database tables that Asterisk (specifically res_config_pgsql
or similar drivers combined with res_pjsip) reads to configure PJSIP objects like
endpoints, AORs (Addresses of Record), and authentication credentials.

Column names MUST match the configuration expected by Asterisk's realtime driver.
Refer to Asterisk PJSIP realtime documentation for specific field requirements.
"""

from sqlalchemy.sql import func
from app.extensions import db

class PjsipEndpointModel(db.Model):
    """
    ARA table for PJSIP endpoint configuration.
    Represents a PJSIP endpoint associated with a specific Call Center Client.
    """
    __tablename__ = 'pjsip_endpoints'

    # PJSIP Endpoint ID (e.g., 'client_alpha_sales'). This is the primary key for Asterisk lookup.
    # It MUST match the corresponding ClientModel.client_identifier.
    id = db.Column(db.String(40), primary_key=True)

    # Foreign key linking back to the logical client record.
    # Ensures data integrity and allows cascade deletion. Unique constraint ensures one-to-one.
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), unique=True, nullable=False)

    # --- PJSIP Configuration Fields (Mirroring pjsip.conf options) ---
    transport = db.Column(db.String(40), nullable=True) # Name of PJSIP transport in res_pjsip.conf
    aors = db.Column(db.String(200), nullable=True) # Comma-separated AOR IDs (usually same as endpoint id)
    auth = db.Column(db.String(40), nullable=True) # Auth section ID for *incoming* authentication (client authenticates TO Asterisk)
    context = db.Column(db.String(80), nullable=False) # Dialplan context for calls *FROM* this endpoint (client initiating call)
    disallow = db.Column(db.String(200), default='all') # Codecs disallowed
    allow = db.Column(db.String(200), default='ulaw,alaw,gsm') # Allowed codecs for calls TO this client
    direct_media = db.Column(db.String(10), default='no') # Controls direct media (RTP path) handling
    outbound_auth = db.Column(db.String(40), nullable=True) # Auth section ID for *outgoing* authentication (Asterisk authenticates TO client)
    from_user = db.Column(db.String(80), nullable=True) # Sets From: header username on outgoing calls
    from_domain = db.Column(db.String(80), nullable=True) # Sets From: header domain on outgoing calls
    callerid = db.Column(db.String(80), nullable=True) # Default CallerID Name <number> format for calls TO this client
    # Add other relevant PJSIP endpoint fields as needed (e.g., timers, rtcp options, message_context)

    # Internal timestamp for tracking updates, potentially useful for debugging ARA cache issues
    config_updated_at = db.Column(db.TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # --- Relationship ---
    # Back-populates the one-to-one link from ClientModel
    client = db.relationship('ClientModel', back_populates='pjsip_endpoint')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<PjsipEndpoint(id='{self.id}', client_id={self.client_id})>"


class PjsipAorModel(db.Model):
    """
    ARA table for PJSIP Address of Record (AOR) configuration.
    Defines where Asterisk can reach a specific PJSIP endpoint (Client).
    """
    __tablename__ = 'pjsip_aors'

    # PJSIP AOR ID (e.g., 'client_alpha_sales'). Primary key. Typically matches the endpoint ID.
    id = db.Column(db.String(40), primary_key=True)
    # Foreign key linking back to the logical client record.
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), unique=True, nullable=False)

    # --- PJSIP Configuration Fields ---
    # The SIP contact URI(s) where Asterisk should send calls for this AOR. Essential field.
    # Example: 'sip:10.10.10.1:5060' or 'sip:user@domain.com;transport=udp'
    contact = db.Column(db.String(255), nullable=False)
    max_contacts = db.Column(db.Integer, default=1) # Max simultaneous registrations for this AOR
    qualify_frequency = db.Column(db.Integer, default=60) # Send OPTIONS requests every N seconds (0=disable)
    # Add other relevant PJSIP AOR fields as needed (e.g., remove_existing, authenticate_qualify)

    # Internal timestamp
    config_updated_at = db.Column(db.TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # --- Relationship ---
    client = db.relationship('ClientModel', back_populates='pjsip_aor')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<PjsipAor(id='{self.id}', contact='{self.contact}')>"


class PjsipAuthModel(db.Model):
    """
    ARA table for PJSIP Authentication configuration.
    Defines credentials used for authenticating PJSIP endpoints (either incoming or outgoing).
    """
    __tablename__ = 'pjsip_auths'

    # PJSIP Auth section ID (e.g., 'auth_for_client_gamma'). Primary key. Referenced by endpoints.
    id = db.Column(db.String(40), primary_key=True)
    # Foreign key linking back to the logical client record.
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), unique=True, nullable=False)

    # --- PJSIP Configuration Fields ---
    auth_type = db.Column(db.String(20), default='userpass') # Authentication type (e.g., userpass, md5)
    username = db.Column(db.String(80), nullable=True) # Username for authentication
    password = db.Column(db.String(128), nullable=True) # Password for authentication
    realm = db.Column(db.String(80), nullable=True) # SIP realm to use/expect for authentication
    # Add other relevant PJSIP auth fields as needed (e.g., md5_cred, nonce_lifetime)

    # Internal timestamp
    config_updated_at = db.Column(db.TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # --- Relationship ---
    client = db.relationship('ClientModel', back_populates='pjsip_auth')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<PjsipAuth(id='{self.id}', username='{self.username}')>"