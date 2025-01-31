# generated by datamodel-codegen:
#   filename:  state_pointset_point.json

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .entry import Entry


class ValueState(Enum):
    """
    State of the individual point
    """

    initializing = 'initializing'
    applied = 'applied'
    updating = 'updating'
    overridden = 'overridden'
    invalid = 'invalid'
    failure = 'failure'


class PointPointsetState(BaseModel):
    """
    Object representation for for a single point
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    units: Optional[str] = Field(
        None,
        description='If specified, indicates a programmed point unit. If empty, means unspecified or matches configured point.',
    )
    value_state: Optional[ValueState] = Field(
        None, description='State of the individual point'
    )
    status: Optional[Entry] = Field(
        None,
        description='Optional status information about this point, subject to log severity level',
    )
