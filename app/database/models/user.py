# app/database/models/user.py
# -*- coding: utf-8 -*-
"""User model representing platform users (Admin, Staff, Seller)."""

from flask_login import UserMixin
from sqlalchemy.sql import func
from sqlalchemy.orm import validates # Added for potential future model validation

from app.extensions import db, bcrypt


class UserModel(UserMixin, db.Model):
    """
    User Model: Represents an Admin, Staff, or Call Seller user.
    Includes Flask-Login integration properties and password hashing.
    """
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(10), nullable=False, index=True) # 'admin', 'staff', 'user'
    status = db.Column(db.String(20), nullable=False, default='active', index=True) # 'active', 'inactive', 'pending_approval', 'suspended'
    full_name = db.Column(db.String(100), nullable=True)
    company_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # --- Relationships ---
    # Call Sellers ('user' role) own DIDs and Campaigns
    # 'lazy=dynamic' allows further filtering on the relationship before loading
    dids = db.relationship('DidModel', back_populates='owner', lazy='dynamic', cascade="all, delete-orphan")
    campaigns = db.relationship('CampaignModel', back_populates='owner', lazy='dynamic', cascade="all, delete-orphan")

    # Admin/Staff create clients ('creator' is the back-pop name in ClientModel)
    created_clients = db.relationship('ClientModel', back_populates='creator', foreign_keys='ClientModel.created_by', lazy='dynamic')

    # User associated with call logs (potentiallynullable link via call_logs.user_id)
    call_logs = db.relationship('CallLogModel', back_populates='user', lazy='dynamic')

    # --- Methods ---
    def __init__(self, username, email, password, role='user', **kwargs):
        """Create instance and hash password."""
        # Ensure Flask-SQLAlchemy handles kwargs properly by calling super().__init__ if needed,
        # or directly assigning non-DB fields. For standard fields, just set them.
        self.username = username
        self.email = email
        self.role = role
        # Set other fields from kwargs if they match columns
        for key, value in kwargs.items():
             if hasattr(self, key): # Basic check if attribute exists
                  setattr(self, key, value)
        # Set password via the dedicated method
        self.set_password(password)


    def set_password(self, password):
        """Set password hash from plaintext password."""
        if not password:
            raise ValueError("Password cannot be empty") # Basic validation
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Check plaintext password against the stored hash."""
        if not self.password_hash or not password:
            return False
        return bcrypt.check_password_hash(self.password_hash, password)

    # --- Flask-Login Properties ---
    @property
    def is_active(self):
        """Required by Flask-Login. Checks if the user's status is 'active'."""
        return self.status == 'active'

    # get_id(), is_authenticated, is_anonymous are provided by UserMixin

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"