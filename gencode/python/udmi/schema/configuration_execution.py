# generated by datamodel-codegen:
#   filename:  configuration_execution.json

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .common import IotProvider
from .configuration_endpoint import EndpointConfiguration


class ExecutionConfiguration(BaseModel):
    """
    Parameters for configuring the execution run of a UDMI tool
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    registry_id: Optional[str] = None
    cloud_region: Optional[str] = None
    site_name: Optional[str] = None
    update_topic: Optional[str] = None
    feed_name: Optional[str] = None
    reflect_region: Optional[str] = None
    site_model: Optional[str] = None
    src_file: Optional[str] = None
    registry_suffix: Optional[str] = None
    shard_count: Optional[int] = None
    shard_index: Optional[int] = None
    device_id: Optional[str] = None
    iot_provider: Optional[IotProvider] = None
    reflector_endpoint: Optional[EndpointConfiguration] = None
    device_endpoint: Optional[EndpointConfiguration] = None
    project_id: Optional[str] = None
    user_name: Optional[str] = None
    udmi_namespace: Optional[str] = None
    bridge_host: Optional[str] = None
    key_file: Optional[str] = None
    serial_no: Optional[str] = None
    log_level: Optional[str] = None
    min_stage: Optional[str] = None
    udmi_version: Optional[str] = Field(
        None, description='Semantic tagged version of udmis install'
    )
    udmi_commit: Optional[str] = Field(
        None, description='Commit hash of this udmis install'
    )
    udmi_ref: Optional[str] = Field(
        None, description='Complete reference of udmis install'
    )
    udmi_timever: Optional[str] = Field(
        None, description='Timestamp version id of udmis install'
    )
    enforce_version: Optional[bool] = None
    udmi_root: Optional[str] = None
    update_to: Optional[str] = Field(
        None, description='Optional version for a udmis update trigger'
    )
    alt_project: Optional[str] = None
    alt_registry: Optional[str] = None
    block_unknown: Optional[bool] = None
    sequences: Optional[List[str]] = None
