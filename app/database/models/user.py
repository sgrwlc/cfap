# -*- coding: utf-8 -*-
"""User model."""

from flask_login import UserMixin
from sqlalchemy.sql import func

from app.extensions import db, bcrypt


class UserModel(UserMixin, db.Model):
    """
    Represents a User in the system (Admin, Staff, or Call Seller).
    Includes Flask-Login integration properties.
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False, index=True) # 'admin', 'staff', 'user'
    status = db.Column(db.String(15), nullable=False, default='active', index=True) # 'active', 'inactive', 'pending_approval', 'suspended'
    full_name = db.Column(db.String(100), nullable=True)
    company_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()) # Relying on DB trigger is also fine

    # Relationships
    # Call Sellers ('user' role) own DIDs and Campaigns
    dids = db.relationship('DidModel', back_populates='owner', lazy='dynamic', cascade="all, delete-orphan")
    campaigns = db.relationship('CampaignModel', back_populates='owner', lazy='dynamic', cascade="all, delete-orphan")
    # Admin/Staff create clients
    created_clients = db.relationship('ClientModel', back_populates='creator', foreign_keys='ClientModel.created_by')
    # User associated with call logs
    call_logs = db.relationship('CallLogModel', back_populates='user', lazy='dynamic')

    def __init__(self, username, email, password, role='user', **kwargs):
        """Create instance."""
        db.Model.__init__(self, username=username, email=email, role=role, **kwargs)
        # Set password using the property setter
        self.set_password(password)

    def set_password(self, password):
        """Set password."""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Check password."""
        return bcrypt.check_password_hash(self.password_hash, password)

    # Flask-Login required properties/methods
    @property
    def is_active(self):
        """Flask-Login: Check if user status is 'active'."""
        return self.status == 'active'

    # get_id is provided by UserMixin (returns self.id)
    # is_authenticated is provided by UserMixin (returns True for logged-in users)
    # is_anonymous is provided by UserMixin (returns False for regular users)

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<User({self.username!r})>"