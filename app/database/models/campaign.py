# -*- coding: utf-8 -*-
"""Campaign related models."""

from sqlalchemy.sql import func
from sqlalchemy.orm import validates
from app.extensions import db


# Association Table Model for Campaign <-> DID (Many-to-Many)
class CampaignDidModel(db.Model):
    __tablename__ = 'campaign_dids'
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='CASCADE'), primary_key=True)
    did_id = db.Column(db.Integer, db.ForeignKey('dids.id', ondelete='CASCADE'), primary_key=True)

    # Relationships to parent objects
    campaign = db.relationship('CampaignModel', back_populates='did_associations')
    did = db.relationship('DidModel', back_populates='campaign_associations')

    def __repr__(self):
        return f"<CampaignDid(Campaign={self.campaign_id}, DID={self.did_id})>"


class CampaignClientSettingsModel(db.Model):
    """Settings for a specific Campaign-Client link."""
    __tablename__ = 'campaign_client_settings'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='CASCADE'), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default='active', index=True) # 'active', 'inactive'
    max_concurrency = db.Column(db.Integer, nullable=False)
    total_calls_allowed = db.Column(db.Integer, nullable=True) # NULL means unlimited
    current_total_calls = db.Column(db.Integer, nullable=False, default=0)
    forwarding_priority = db.Column(db.Integer, nullable=False, default=0, index=True)
    weight = db.Column(db.Integer, nullable=False, default=100)
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    campaign = db.relationship('CampaignModel', back_populates='client_settings')
    client = db.relationship('ClientModel', back_populates='campaign_settings')

    # Link to call logs using this specific setting
    call_logs = db.relationship('CallLogModel', back_populates='campaign_client_setting', lazy='dynamic')

    # Ensure weight is positive
    @validates('weight')
    def validate_weight(self, key, weight):
        if weight <= 0:
            raise ValueError("Weight must be positive")
        return weight

    # Ensure max_concurrency is positive
    @validates('max_concurrency')
    def validate_max_concurrency(self, key, max_concurrency):
        if max_concurrency < 1:
            raise ValueError("Max concurrency must be at least 1")
        return max_concurrency

    def __repr__(self):
        return f"<CampaignClientSetting(Campaign={self.campaign_id}, Client={self.client_id}, Prio={self.forwarding_priority})>"


class CampaignModel(db.Model):
    """Represents a Call Seller's campaign."""
    __tablename__ = 'campaigns'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(10), nullable=False, default='active', index=True) # 'active', 'inactive', 'paused'
    routing_strategy = db.Column(db.String(20), nullable=False, default='priority') # 'priority', 'round_robin', 'weighted'
    dial_timeout_seconds = db.Column(db.Integer, nullable=False, default=30)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Define unique constraint for user_id and name
    __table_args__ = (db.UniqueConstraint('user_id', 'name', name='uq_user_campaign_name'),)

    # Relationships
    owner = db.relationship('UserModel', back_populates='campaigns')

    # Many-to-Many with DIDs via association object
    did_associations = db.relationship('CampaignDidModel', back_populates='campaign', cascade="all, delete-orphan")
    # Easily get DIDs directly (optional helper)
    # dids = association_proxy('did_associations', 'did') # Requires Association Proxy extension

    # One-to-Many with CampaignClientSettings
    client_settings = db.relationship('CampaignClientSettingsModel', back_populates='campaign', lazy='dynamic', cascade="all, delete-orphan", order_by='CampaignClientSettingsModel.forwarding_priority')

    # Link to call logs related to this campaign
    call_logs = db.relationship('CallLogModel', back_populates='campaign', lazy='dynamic')

    # Ensure dial_timeout_seconds is positive
    @validates('dial_timeout_seconds')
    def validate_dial_timeout(self, key, timeout):
        if timeout <= 0:
            raise ValueError("Dial timeout must be positive")
        return timeout

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<Campaign({self.name!r})>"