# app/database/models/campaign.py
# -*- coding: utf-8 -*-
"""Campaign related database models."""

from sqlalchemy.sql import func
from sqlalchemy.orm import validates
from app.extensions import db
from sqlalchemy.ext.associationproxy import association_proxy


# Association Table Model for Campaign <-> DID (Many-to-Many)
class CampaignDidModel(db.Model):
    """Association table linking Campaigns and DIDs."""
    __tablename__ = 'campaign_dids'
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='CASCADE'), primary_key=True)
    did_id = db.Column(db.Integer, db.ForeignKey('dids.id', ondelete='CASCADE'), primary_key=True)

    # Relationships to parent objects for easier navigation if needed
    campaign = db.relationship('CampaignModel', back_populates='did_associations')
    did = db.relationship('DidModel', back_populates='campaign_associations')

    def __repr__(self):
        return f"<CampaignDid(Campaign={self.campaign_id}, DID={self.did_id})>"


class CampaignClientSettingsModel(db.Model):
    """
    Settings for a specific link between a Campaign and a Client.
    Defines routing behavior (priority, weight) and caps (concurrency, total) for that link.
    """
    __tablename__ = 'campaign_client_settings'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default='active', index=True) # 'active', 'inactive'
    max_concurrency = db.Column(db.Integer, nullable=False) # Must be >= 1
    total_calls_allowed = db.Column(db.Integer, nullable=True) # NULL means unlimited
    current_total_calls = db.Column(db.Integer, nullable=False, default=0) # Counter incremented by logging service
    forwarding_priority = db.Column(db.Integer, nullable=False, default=0, index=True) # Lower number = higher priority
    weight = db.Column(db.Integer, nullable=False, default=100) # Must be > 0
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # --- Relationships ---
    campaign = db.relationship('CampaignModel', back_populates='client_settings')
    client = db.relationship('ClientModel', back_populates='campaign_settings')

    # Link to call logs using this specific setting (potentially nullable link via call_logs FK)
    call_logs = db.relationship('CallLogModel', back_populates='campaign_client_setting', lazy='dynamic')

    # --- Model-Level Validation ---
    @validates('weight')
    def validate_weight(self, key, weight):
        """Ensure weight is positive."""
        if not isinstance(weight, int) or weight <= 0:
            raise ValueError("Weight must be a positive integer")
        return weight

    @validates('max_concurrency')
    def validate_max_concurrency(self, key, max_concurrency):
        """Ensure max_concurrency is at least 1."""
        if not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise ValueError("Max concurrency must be an integer of at least 1")
        return max_concurrency

    @validates('total_calls_allowed')
    def validate_total_calls_allowed(self, key, total_calls):
        """Ensure total_calls_allowed is non-negative if not None."""
        if total_calls is not None and (not isinstance(total_calls, int) or total_calls < 0):
             raise ValueError("Total calls allowed must be a non-negative integer or null")
        return total_calls

    def __repr__(self):
        return f"<CampaignClientSetting(id={self.id}, Campaign={self.campaign_id}, Client={self.client_id}, Prio={self.forwarding_priority})>"


class CampaignModel(db.Model):
    """Represents a Call Seller's campaign."""
    __tablename__ = 'campaigns'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(10), nullable=False, default='active', index=True) # 'active', 'inactive', 'paused'
    routing_strategy = db.Column(db.String(20), nullable=False, default='priority') # 'priority', 'round_robin', 'weighted'
    dial_timeout_seconds = db.Column(db.Integer, nullable=False, default=30) # Must be > 0
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Define unique constraint for user_id and name
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='uq_user_campaign_name'),)

    # --- Relationships ---
    owner = db.relationship('UserModel', back_populates='campaigns')

    # Many-to-Many with DIDs via association object
    # cascade="all, delete-orphan" ensures CampaignDidModel entries are deleted when a Campaign is deleted
    did_associations = db.relationship('CampaignDidModel', back_populates='campaign', cascade="all, delete-orphan", lazy="dynamic") # Use lazy=dynamic if needed
    # Easily get DIDs directly using association proxy (requires import)
    dids = association_proxy('did_associations', 'did')

    # One-to-Many with CampaignClientSettings
    # cascade="all, delete-orphan" ensures settings are deleted when campaign is deleted
    # Order by priority by default when accessing the relationship
    client_settings = db.relationship(
        'CampaignClientSettingsModel',
        back_populates='campaign',
        lazy='dynamic', # Or 'selectin' if often loaded together
        cascade="all, delete-orphan",
        order_by='CampaignClientSettingsModel.forwarding_priority'
    )

    # Link to call logs related to this campaign (potentially nullable link)
    call_logs = db.relationship('CallLogModel', back_populates='campaign', lazy='dynamic')

    # --- Model-Level Validation ---
    @validates('dial_timeout_seconds')
    def validate_dial_timeout(self, key, timeout):
        """Ensure dial_timeout_seconds is positive."""
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("Dial timeout must be a positive integer")
        return timeout

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<Campaign(id={self.id}, name='{self.name}', user_id={self.user_id})>"