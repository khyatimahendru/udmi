# generated by datamodel-codegen:
#   filename:  events_discovery.json
#   timestamp: 2025-01-31T07:45:30+00:00

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, constr

from .ancillary_properties import AncillaryProperties
from .discovery_family import FamilyDiscovery
from .discovery_feature import FeatureDiscovery
from .discovery_ref import RefDiscovery
from .entry import Entry
from .model_cloud import CloudModel
from .model_pointset_point import PointPointsetModel
from .state_system_hardware import StateSystemHardware


class System(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    description: Optional[str] = Field(
        None, description='Full textual desctiiption of this device'
    )
    name: Optional[str] = Field(None, description='Friendly name of this device')
    serial_no: Optional[str] = Field(
        None, description='The serial number of the physical device'
    )
    ancillary: Optional[AncillaryProperties] = None
    hardware: Optional[StateSystemHardware] = None


class DiscoveryEvents(BaseModel):
    """
    [Discovery result](../docs/specs/discovery.md) with implicit discovery
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    timestamp: Optional[datetime] = Field(
        None,
        description='RFC 3339 UTC timestamp the discover telemetry event was generated',
        examples=['2019-01-17T14:02:29.364Z'],
    )
    version: Optional[str] = Field(None, description='Version of the UDMI schema')
    generation: Optional[datetime] = Field(
        None,
        description="The event's discovery scan trigger's generation timestamp",
        examples=['2019-01-17T14:02:29.364Z'],
    )
    status: Optional[Entry] = None
    scan_family: Optional[Any] = None
    scan_addr: Optional[str] = Field(
        None, description='The primary address of the device (for scan_family)'
    )
    event_no: Optional[int] = Field(
        None,
        description='The active or passive series number of this result (matches reported state values)',
    )
    families: Optional[
        Dict[constr(pattern=r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$'), FamilyDiscovery]
    ] = Field(None, description='Links to other address families (family and id)')
    registries: Optional[
        Dict[constr(pattern=r'^[A-Z]{2,6}-[1-9][0-9]*$'), CloudModel]
    ] = Field(None, description='Registry discovery results.')
    devices: Optional[Dict[constr(pattern=r'^[A-Z]{2,6}-[1-9][0-9]*$'), CloudModel]] = (
        Field(None, description='Device iot discovery scan results.')
    )
    points: Optional[
        Dict[constr(pattern=r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$'), PointPointsetModel]
    ] = Field(
        None, description='Information about a specific point name of the device.'
    )
    refs: Optional[Dict[constr(pattern=r'^[-_.:/a-zA-Z0-9]+$'), RefDiscovery]] = Field(
        None, description='Collection of point references discovered'
    )
    features: Optional[Dict[constr(pattern=r'^[._a-zA-Z]+$'), FeatureDiscovery]] = (
        Field(None, description='Discovery of features supported by this device.')
    )
    cloud_model: Optional[CloudModel] = None
    system: Optional[System] = Field(None, title='System Discovery Data')
