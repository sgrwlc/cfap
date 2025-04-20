# -*- coding: utf-8 -*-
"""PJSIP Configuration models for Asterisk Realtime Architecture (ARA)."""

from sqlalchemy.sql import func
from app.extensions import db

# Note: Column names MUST match the configuration expected by Asterisk's
# res_pjsip_config_wizard.so or equivalent real-time driver (e.g., res_config_pgsql.so).
# Check your Asterisk PJSIP realtime configuration documentation.

class PjsipEndpointModel(db.Model):
    """ARA table for PJSIP endpoint configuration."""
    __tablename__ = 'pjsip_endpoints'

    # PJSIP Endpoint ID, must match clients.client_identifier. This is the primary key.
    id = db.Column(db.String(40), primary_key=True)
    # Link back to the logical client (ensures uniqueness and allows cascade delete)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), unique=True, nullable=False)

    transport = db.Column(db.String(40), nullable=True) # Name of PJSIP transport
    aors = db.Column(db.String(200), nullable=True) # Comma-separated AOR IDs (often same as endpoint id)
    auth = db.Column(db.String(40), nullable=True) # Auth section ID for incoming auth (if client authenticates TO us)
    context = db.Column(db.String(80), nullable=False) # Dialplan context for calls FROM this endpoint
    disallow = db.Column(db.String(200), default='all')
    allow = db.Column(db.String(200), default='ulaw,alaw,gsm') # Allowed codecs for calls TO this client
    direct_media = db.Column(db.String(10), default='no')
    outbound_auth = db.Column(db.String(40), nullable=True) # Auth section ID for outbound auth (if WE authenticate TO them)
    from_user = db.Column(db.String(80), nullable=True)
    from_domain = db.Column(db.String(80), nullable=True)
    callerid = db.Column(db.String(80), nullable=True) # Default CallerID Name <number> format
    # Add other relevant PJSIP endpoint fields as needed by your Asterisk version/config

    config_updated_at = db.Column(db.TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship back to the logical client
    client = db.relationship('ClientModel', back_populates='pjsip_endpoint')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<PjsipEndpoint({self.id!r})>"


class PjsipAorModel(db.Model):
    """ARA table for PJSIP Address of Record (AOR) configuration."""
    __tablename__ = 'pjsip_aors'

    # PJSIP AOR ID, typically matches the endpoint ID. Primary key.
    id = db.Column(db.String(40), primary_key=True)
    # Link back to the logical client
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), unique=True, nullable=False)

    contact = db.Column(db.String(255), nullable=False) # SIP URI(s) of the client (e.g., 'sip:host:port')
    max_contacts = db.Column(db.Integer, default=1)
    qualify_frequency = db.Column(db.Integer, default=60)
    # Add other relevant PJSIP AOR fields as needed

    config_updated_at = db.Column(db.TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship back to the logical client
    client = db.relationship('ClientModel', back_populates='pjsip_aor')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<PjsipAor({self.id!r})>"


class PjsipAuthModel(db.Model):
    """ARA table for PJSIP Authentication configuration."""
    __tablename__ = 'pjsip_auths'

    # PJSIP Auth section ID, referenced by endpoints. Primary key.
    id = db.Column(db.String(40), primary_key=True)
    # Link back to the logical client
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), unique=True, nullable=False)

    auth_type = db.Column(db.String(20), default='userpass')
    username = db.Column(db.String(80), nullable=True)
    password = db.Column(db.String(128), nullable=True) # Store the password needed for SIP auth
    realm = db.Column(db.String(80), nullable=True) # SIP realm
    # Add other relevant PJSIP auth fields as needed

    config_updated_at = db.Column(db.TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship back to the logical client
    client = db.relationship('ClientModel', back_populates='pjsip_auth')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<PjsipAuth({self.id!r})>"