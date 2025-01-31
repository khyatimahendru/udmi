# generated by datamodel-codegen:
#   filename:  config_discovery.json
#   timestamp: 2025-01-31T07:45:30+00:00

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, constr

from .common import Depth
from .config_discovery_family import FamilyDiscoveryConfig


class Enumerations(BaseModel):
    """
    Enumeration depth for self-enumerations.
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    families: Optional[Depth] = None
    devices: Optional[Depth] = None
    points: Optional[Depth] = None
    features: Optional[Depth] = None


class DiscoveryConfig(BaseModel):
    """
    Configuration for [discovery](../docs/specs/discovery.md)
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    generation: Optional[datetime] = Field(
        None, description='Generational marker for controlling enumeration'
    )
    enumerations: Optional[Enumerations] = Field(
        None, description='Enumeration depth for self-enumerations.'
    )
    families: Optional[
        Dict[constr(pattern=r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$'), FamilyDiscoveryConfig]
    ] = Field(None, description='Address family configs for discovery scans.')
