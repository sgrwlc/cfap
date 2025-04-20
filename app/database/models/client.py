# -*- coding: utf-8 -*-
"""Client (Call Center) model."""

from sqlalchemy.sql import func
from app.extensions import db

class ClientModel(db.Model):
    """Logical representation of a Call Center client."""
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    client_identifier = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    department = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(10), nullable=False, default='active', index=True) # 'active', 'inactive'
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    creator = db.relationship('UserModel', back_populates='created_clients')

    # Link to PJSIP configuration tables (one-to-one via client_id foreign key in PJSIP tables)
    pjsip_endpoint = db.relationship('PjsipEndpointModel', back_populates='client', uselist=False, cascade="all, delete-orphan")
    pjsip_aor = db.relationship('PjsipAorModel', back_populates='client', uselist=False, cascade="all, delete-orphan")
    pjsip_auth = db.relationship('PjsipAuthModel', back_populates='client', uselist=False, cascade="all, delete-orphan")

    # Link to campaign settings where this client is used
    campaign_settings = db.relationship('CampaignClientSettingsModel', back_populates='client', lazy='dynamic', cascade="all, delete-orphan")

    # Link to call logs where this client was involved
    call_logs = db.relationship('CallLogModel', back_populates='client', lazy='dynamic')


    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<Client({self.client_identifier!r})>"