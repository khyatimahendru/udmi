# generated by datamodel-codegen:
#   filename:  configuration_endpoint.json

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, constr


class Protocol(Enum):
    local = 'local'
    pubsub = 'pubsub'
    file = 'file'
    trace = 'trace'
    mqtt = 'mqtt'


class Transport(Enum):
    ssl = 'ssl'
    tcp = 'tcp'


class Basic(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    username: Optional[str] = None
    password: Optional[str] = None


class Jwt(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    audience: Optional[str] = None


class AuthProvider(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    basic: Optional[Basic] = None
    jwt: Optional[Jwt] = None


class EndpointConfiguration(BaseModel):
    """
    Parameters to define a message endpoint
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    name: Optional[str] = Field(
        None, description='Friendly name for this flow (debugging and diagnostics)'
    )
    protocol: Optional[Protocol] = None
    transport: Optional[Transport] = None
    hostname: Optional[str] = None
    payload: Optional[str] = Field(
        None, description='Simple payload template for simple injection use cases'
    )
    error: Optional[str] = Field(
        None,
        description='Error message container for capturing errors during parsing/handling',
    )
    port: Optional[int] = None
    config_sync_sec: Optional[int] = Field(
        None,
        description='Delay waiting for config message on start, 0 for default, <0 to disable',
    )
    client_id: Optional[str] = None
    topic_prefix: Optional[constr(pattern=r'^[-_/a-zA-Z0-9]+$')] = Field(
        None, description='Prefix for message topics'
    )
    recv_id: Optional[constr(pattern=r'^[-_/a-zA-Z0-9#]+$')] = Field(
        None, description='Id for the receiving message channel'
    )
    send_id: Optional[constr(pattern=r'^[-_/a-zA-Z0-9#]+$')] = Field(
        None, description='Id for the sending messages channel'
    )
    side_id: Optional[constr(pattern=r'^[-_/a-zA-Z0-9#]+$')] = Field(
        None, description='Id for a side-car message channel'
    )
    gatewayId: Optional[str] = None
    deviceId: Optional[str] = None
    enabled: Optional[str] = Field(
        None,
        description='Indicator if this endpoint should be active (null or non-empty)',
    )
    noConfigAck: Optional[bool] = Field(
        None, description='True if config messages should not be acked (lower QOS)'
    )
    capacity: Optional[int] = Field(
        None, description='Queue capacity for limiting pipes'
    )
    publish_delay_sec: Optional[int] = Field(
        None, description='Artifical publish delay for testing'
    )
    periodic_sec: Optional[int] = Field(
        None, description='Rate for periodic task execution'
    )
    keyBytes: Optional[Any] = None
    algorithm: Optional[str] = None
    auth_provider: Optional[AuthProvider] = None
    generation: Optional[datetime] = Field(
        None,
        description='The timestamp of the endpoint generation',
        examples=['2019-01-17T14:02:29.364Z'],
    )
