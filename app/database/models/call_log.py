# app/database/models/call_log.py
# -*- coding: utf-8 -*-
"""Call Log model for storing Call Detail Records (CDRs)."""

from sqlalchemy.sql import func
from app.extensions import db

class CallLogModel(db.Model):
    """
    Detailed record of a call attempt processed by the system.
    Typically populated via an internal API called by Asterisk AGI.
    """
    __tablename__ = 'call_logs'

    # Use BigInteger for potentially very large log tables
    id = db.Column(db.BigInteger, primary_key=True)

    # --- Foreign Keys (linking to other entities) ---
    # Use SET NULL on delete: if related entity is deleted, keep the log but nullify the link.
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True, nullable=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='SET NULL'), index=True, nullable=True)
    did_id = db.Column(db.Integer, db.ForeignKey('dids.id', ondelete='SET NULL'), index=True, nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='SET NULL'), index=True, nullable=True) # Client attempted/connected
    campaign_client_setting_id = db.Column(db.Integer, db.ForeignKey('campaign_client_settings.id', ondelete='SET NULL'), nullable=True) # Specific setting used

    # --- Call Information ---
    incoming_did_number = db.Column(db.String(50), nullable=False, index=True) # The number that was dialed
    caller_id_num = db.Column(db.String(50), nullable=True) # Caller's phone number
    caller_id_name = db.Column(db.String(100), nullable=True) # Caller's name (if available)

    # --- Timestamps (with Timezone) ---
    timestamp_start = db.Column(db.TIMESTAMP(timezone=True), nullable=False, index=True) # Call arrival time
    timestamp_answered = db.Column(db.TIMESTAMP(timezone=True), nullable=True) # Time call was answered (if applicable)
    timestamp_end = db.Column(db.TIMESTAMP(timezone=True), nullable=True) # Time call ended

    # --- Durations ---
    duration_seconds = db.Column(db.Integer, nullable=True) # Total duration from start to end
    billsec_seconds = db.Column(db.Integer, nullable=True) # Duration after answer (billed duration)

    # --- Call Status & Outcome ---
    # Examples: ANSWERED, NOANSWER, BUSY, FAILED, REJECTED_CC, REJECTED_TOTAL, REJECTED_DID, etc.
    call_status = db.Column(db.String(50), nullable=False, index=True)
    hangup_cause_code = db.Column(db.Integer, nullable=True) # Asterisk hangup cause code
    hangup_cause_text = db.Column(db.String(50), nullable=True) # Text description of hangup cause

    # --- Asterisk Specific Identifiers ---
    # Should be unique from Asterisk's perspective for a single call leg
    asterisk_uniqueid = db.Column(db.String(50), unique=True, index=True, nullable=True)
    # Used to link related call legs (e.g., incoming leg to outgoing leg)
    asterisk_linkedid = db.Column(db.String(50), index=True, nullable=True)

    # --- Record Timestamps ---
    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # --- Relationships ---
    # Define relationships to easily access linked objects from a log entry
    user = db.relationship('UserModel', back_populates='call_logs')
    campaign = db.relationship('CampaignModel', back_populates='call_logs')
    did = db.relationship('DidModel', back_populates='call_logs')
    client = db.relationship('ClientModel', back_populates='call_logs')
    campaign_client_setting = db.relationship('CampaignClientSettingsModel', back_populates='call_logs')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<CallLog(id={self.id}, AsteriskUID='{self.asterisk_uniqueid}', DID='{self.incoming_did_number}', Status='{self.call_status}')>"