# generated by datamodel-codegen:
#   filename:  common.json

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Mode(Enum):
    """
    Operating mode for the device. Default is 'active'.
    """

    initial = 'initial'
    active = 'active'
    updating = 'updating'
    restart = 'restart'
    terminate = 'terminate'
    shutdown = 'shutdown'


Family = Optional[str]


class Depth(Enum):
    buckets = 'buckets'
    entries = 'entries'
    details = 'details'
    parts = 'parts'


class IotProvider(Enum):
    local = 'local'
    dynamic = 'dynamic'
    implicit = 'implicit'
    pubsub = 'pubsub'
    mqtt = 'mqtt'
    gbos = 'gbos'
    gref = 'gref'
    etcd = 'etcd'
    jwt = 'jwt'
    clearblade = 'clearblade'


class Stage(Enum):
    """
    Stage of a feature implemenation
    """

    disabled = 'disabled'
    alpha = 'alpha'
    preview = 'preview'
    beta = 'beta'
    stable = 'stable'


class Phase(Enum):
    """
    Phase for the management of a configuration blob.
    """

    apply = 'apply'
    final = 'final'


class Blobsets(Enum):
    """
    Predefined system blobsets
    """

    field_iot_endpoint_config = '_iot_endpoint_config'


@dataclass
class Common:
    family: Optional[Family] = None
