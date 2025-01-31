# generated by datamodel-codegen:
#   filename:  state_gateway.json

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .entry import Entry


class GatewayState(BaseModel):
    """
    [Gateway Documentation](../docs/specs/gateway.md)
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    timestamp: Optional[datetime] = Field(
        None,
        description='Not included in messages published by devices. Part of message subblocks within cloud pipeline. RFC 3339 Timestamp the payload was generated',
        examples=['2019-01-17T14:02:29.364Z'],
    )
    version: Optional[str] = Field(None, description='Version of the UDMI schema')
    status: Optional[Entry] = None
