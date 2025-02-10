# generated by datamodel-codegen:
#   filename:  configuration_pubber.json

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .configuration_endpoint import EndpointConfiguration
from .options_pubber import PubberOptions


@dataclass
class PubberConfiguration:
    """
    Parameters to define a pubber runtime instance
    """

    endpoint: Optional[EndpointConfiguration] = None
    iotProject: Optional[str] = None
    projectId: Optional[str] = None
    registryId: Optional[str] = None
    deviceId: Optional[str] = None
    gatewayId: Optional[str] = None
    sitePath: Optional[str] = None
    keyFile: Optional[str] = 'local/rsa_private.pkcs8'
    algorithm: Optional[str] = 'RS256'
    serialNo: Optional[str] = None
    macAddr: Optional[str] = None
    keyBytes: Optional[Any] = None
    options: Optional[PubberOptions] = None
