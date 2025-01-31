# generated by datamodel-codegen:
#   filename:  events_validation_device.json

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .entry import Entry


class DeviceValidationEvents(BaseModel):
    """
    Validation summary information for an individual device.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    last_seen: Optional[datetime] = Field(
        None, description='Last time any message from this device was received'
    )
    oldest_mark: Optional[datetime] = Field(
        None, description='Oldest recorded mark for this device'
    )
    status: Optional[Entry] = None
