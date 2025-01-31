# generated by datamodel-codegen:
#   filename:  access_iot.json
#   timestamp: 2025-01-31T07:45:30+00:00

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from .common import IotProvider


class IotAccess(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    name: Optional[str] = None
    provider: Optional[IotProvider] = None
    project_id: Optional[str] = None
    profile_sec: Optional[int] = None
    options: Optional[str] = None
