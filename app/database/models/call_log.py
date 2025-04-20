# -*- coding: utf-8 -*-
"""Call Log model."""

from sqlalchemy.sql import func
from app.extensions import db

class CallLogModel(db.Model):
    """Detailed record of a call attempt."""
    __tablename__ = 'call_logs'

    id = db.Column(db.BigInteger, primary_key=True) # Use BigInteger for potentially large tables
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), index=True, nullable=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id', ondelete='SET NULL'), index=True, nullable=True)
    did_id = db.Column(db.Integer, db.ForeignKey('dids.id', ondelete='SET NULL'), index=True, nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id', ondelete='SET NULL'), index=True, nullable=True)
    campaign_client_setting_id = db.Column(db.Integer, db.ForeignKey('campaign_client_settings.id', ondelete='SET NULL'), nullable=True)

    incoming_did_number = db.Column(db.String(50), nullable=False, index=True)
    caller_id_num = db.Column(db.String(50), nullable=True)
    caller_id_name = db.Column(db.String(100), nullable=True)

    timestamp_start = db.Column(db.TIMESTAMP(timezone=True), nullable=False, index=True)
    timestamp_answered = db.Column(db.TIMESTAMP(timezone=True), nullable=True)
    timestamp_end = db.Column(db.TIMESTAMP(timezone=True), nullable=True)

    duration_seconds = db.Column(db.Integer, nullable=True)
    billsec_seconds = db.Column(db.Integer, nullable=True)

    call_status = db.Column(db.String(50), nullable=False, index=True) # e.g., ANSWERED, NOANSWER, BUSY, FAILED, REJECTED_CC, REJECTED_TOTAL
    hangup_cause_code = db.Column(db.Integer, nullable=True)
    hangup_cause_text = db.Column(db.String(50), nullable=True)

    asterisk_uniqueid = db.Column(db.String(50), unique=True, index=True, nullable=True) # Should be unique from Asterisk
    asterisk_linkedid = db.Column(db.String(50), index=True, nullable=True)

    created_at = db.Column(db.TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    user = db.relationship('UserModel', back_populates='call_logs')
    campaign = db.relationship('CampaignModel', back_populates='call_logs')
    did = db.relationship('DidModel', back_populates='call_logs')
    client = db.relationship('ClientModel', back_populates='call_logs')
    campaign_client_setting = db.relationship('CampaignClientSettingsModel', back_populates='call_logs')

    def __repr__(self):
        """Represent instance as a unique string."""
        return f"<CallLog({self.id}, DID={self.incoming_did_number}, Status={self.call_status})>"