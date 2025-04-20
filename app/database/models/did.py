# -*- coding: utf-8 -*-
"""DID (Phone Number) model."""

from sqlalchemy.sql import func
from app.extensions import db

class DidModel(db.Model):
    """Represents a phone number (DID) owned by a Call Seller."""
    __tablename__ = 'dids'

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default='active', index=True) # 'active', 'inactive'
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = db.relationship('UserModel', back_populates='dids')
    # Link to campaigns this DID is part of (via association object)
    campaign_associations = db.relationship('CampaignDidModel', back_populates='did', cascade="all, delete-orphan")
    # Easily get campaigns directly (optional helper)
    # campaigns = association_proxy('campaign_associations', 'campaign') # Requires Association Proxy extension

    # Link to call logs involving this DID
    call_logs = db.relationship('CallLogModel', back_populates='did', lazy='dynamic')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<Did({self.number!r})>"