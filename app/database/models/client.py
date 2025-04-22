# app/database/models/client.py
# -*- coding: utf-8 -*-
"""Client model representing a Call Center entity."""

from sqlalchemy.sql import func
from app.extensions import db

class ClientModel(db.Model):
    """
    Logical representation of a Call Center client.
    Linked one-to-one with corresponding PJSIP configuration entities for Asterisk ARA.
    """
    __tablename__ = 'clients'

    id = db.Column(db.Integer, primary_key=True)
    # Unique identifier used for linking, potentially PJSIP endpoint name
    client_identifier = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    department = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(10), nullable=False, default='active', index=True) # 'active', 'inactive'
    notes = db.Column(db.Text, nullable=True)
    # Link to the user (Admin/Staff) who created this client record
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # --- Relationships ---
    # Relationship to the creator user
    creator = db.relationship('UserModel', back_populates='created_clients')

    # One-to-One relationships to PJSIP configuration tables.
    # 'uselist=False' defines the one-to-one nature.
    # 'cascade="all, delete-orphan"' ensures PJSIP records are deleted when the client is deleted.
    pjsip_endpoint = db.relationship('PjsipEndpointModel', back_populates='client', uselist=False, cascade="all, delete-orphan")
    pjsip_aor = db.relationship('PjsipAorModel', back_populates='client', uselist=False, cascade="all, delete-orphan")
    pjsip_auth = db.relationship('PjsipAuthModel', back_populates='client', uselist=False, cascade="all, delete-orphan")

    # One-to-Many relationship to campaign settings where this client is used.
    # 'lazy=dynamic' allows further filtering on the collection.
    # 'cascade="all, delete-orphan"' ensures linking records are deleted if the client is deleted.
    campaign_settings = db.relationship('CampaignClientSettingsModel', back_populates='client', lazy='dynamic', cascade="all, delete-orphan")

    # One-to-Many relationship to call logs where this client was involved.
    # 'lazy=dynamic' is suitable for potentially large numbers of logs.
    call_logs = db.relationship('CallLogModel', back_populates='client', lazy='dynamic')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<Client(id={self.id}, identifier='{self.client_identifier}', name='{self.name}')>"