# generated by datamodel-codegen:
#   filename:  state_discovery_family.json
#   timestamp: 2025-01-31T07:45:30+00:00

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, conint

from .entry import Entry


class Phase(Enum):
    """
    Current phase of an active discovery process
    """

    stopped = 'stopped'
    pending = 'pending'
    active = 'active'


class FamilyDiscoveryState(BaseModel):
    """
    State for [discovery](../docs/specs/discovery.md)
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    generation: Optional[datetime] = Field(
        None, description='Generational marker for reporting discovery'
    )
    phase: Optional[Phase] = Field(
        None, description='Current phase of an active discovery process'
    )
    active_count: Optional[conint(ge=0)] = Field(
        None,
        description='Number of records produced so far for this active scan generation',
    )
    passive_count: Optional[conint(ge=0)] = Field(
        None, description="Number of passive scan results currently 'on hold'"
    )
    status: Optional[Entry] = Field(
        None, description='Status information about the discovery operation'
    )
