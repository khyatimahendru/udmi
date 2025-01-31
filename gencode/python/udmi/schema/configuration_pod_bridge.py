# generated by datamodel-codegen:
#   filename:  configuration_pod_bridge.json

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .configuration_endpoint import EndpointConfiguration


class BridgePodConfiguration(BaseModel):
    """
    Parameters to define a bridge between message domains
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    enabled: Optional[str] = None
    from_: Optional[EndpointConfiguration] = Field(None, alias='from')
    morf: Optional[EndpointConfiguration] = None
