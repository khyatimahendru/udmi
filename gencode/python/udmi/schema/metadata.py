# generated by datamodel-codegen:
#   filename:  metadata.json
#   timestamp: 2025-01-31T07:45:30+00:00

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, constr

from .events_discovery import DiscoveryEvents
from .model_cloud import CloudModel
from .model_discovery import DiscoveryModel
from .model_features import TestingModel as TestingModel_1
from .model_gateway import GatewayModel
from .model_localnet import LocalnetModel
from .model_pointset import PointsetModel
from .model_system import SystemModel
from .model_testing import TestingModel


class Metadata(BaseModel):
    """
    [Metadata](../docs/specs/metadata.md) is a description about the device: a specification about how the device should be configured and expectations about what the device should be doing. Defined by `metadata.json`
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    timestamp: Optional[datetime] = Field(
        None,
        description='RFC 3339 timestamp UTC the data was generated',
        examples=['2019-01-17T14:02:29.364Z'],
    )
    version: Optional[str] = Field(
        None, description='Version of the UDMI schema for this file'
    )
    upgraded_from: Optional[str] = Field(
        None, description='Original version of the UDMI schema for this file'
    )
    hash: Optional[constr(pattern=r'^[0-9a-z]{8}$')] = Field(
        None,
        description='Automatically generated field that contains the hash of file contents.',
    )
    cloud: Optional[CloudModel] = None
    system: Optional[SystemModel] = None
    gateway: Optional[GatewayModel] = None
    discovery: Optional[DiscoveryModel] = None
    localnet: Optional[LocalnetModel] = None
    testing: Optional[TestingModel] = None
    features: Optional[TestingModel_1] = None
    pointset: Optional[PointsetModel] = None
    families: Optional[
        Dict[constr(pattern=r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$'), DiscoveryEvents]
    ] = None
