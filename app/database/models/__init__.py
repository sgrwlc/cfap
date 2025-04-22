# app/database/models/__init__.py
# -*- coding: utf-8 -*-
"""
Models Package Initialization.

Exposes model classes for easier importing throughout the application,
e.g., `from app.database.models import UserModel`.
"""

# Import models from their respective files to make them available directly
from .user import UserModel
from .client import ClientModel
from .pjsip import PjsipEndpointModel, PjsipAorModel, PjsipAuthModel
from .did import DidModel
from .campaign import CampaignModel, CampaignDidModel, CampaignClientSettingsModel
from .call_log import CallLogModel

# Optional: Define __all__ to control wildcard imports (`from .models import *`)
# This explicitly lists the models intended for public use from this package.
__all__ = [
    'UserModel',
    'ClientModel',
    'PjsipEndpointModel',
    'PjsipAorModel',
    'PjsipAuthModel',
    'DidModel',
    'CampaignModel',
    'CampaignDidModel',
    'CampaignClientSettingsModel',
    'CallLogModel',
]