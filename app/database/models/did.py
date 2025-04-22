# app/database/models/did.py
# -*- coding: utf-8 -*-
"""DID (Direct Inward Dialing) phone number model."""

from sqlalchemy.sql import func
from app.extensions import db
# from sqlalchemy.ext.associationproxy import association_proxy # If using proxy for campaigns

class DidModel(db.Model):
    """
    Represents a phone number (DID) owned by a Call Seller (User).
    Can be linked to one or more Campaigns.
    """
    __tablename__ = 'dids'

    id = db.Column(db.Integer, primary_key=True)
    # The phone number itself, should be unique system-wide. E.g., '+15551234567'
    number = db.Column(db.String(50), unique=True, nullable=False, index=True)
    # Foreign key linking to the user who owns this DID
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False, default='active', index=True) # 'active', 'inactive'
    description = db.Column(db.String(255), nullable=True) # User-friendly label
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # --- Relationships ---
    # Relationship to the owner (UserModel)
    owner = db.relationship('UserModel', back_populates='dids')

    # Many-to-Many relationship link to campaigns via the CampaignDidModel association table.
    # 'cascade="all, delete-orphan"' ensures the link entries are deleted if the DID is deleted.
    campaign_associations = db.relationship('CampaignDidModel', back_populates='did', cascade="all, delete-orphan", lazy="dynamic")

    # Optional: Use association_proxy to directly access linked campaigns
    # campaigns = association_proxy('campaign_associations', 'campaign')

    # One-to-Many relationship to call logs involving this DID (as the incoming number)
    call_logs = db.relationship('CallLogModel', back_populates='did', lazy='dynamic')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<Did(id={self.id}, number='{self.number}', user_id={self.user_id})>"