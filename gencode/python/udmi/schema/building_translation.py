# generated by datamodel-codegen:
#   filename:  building_translation.json

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class BuildingTranslation(BaseModel):
    """
    [Discovery result](../docs/specs/discovery.md) with implicit enumeration
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    present_value: Optional[str] = Field(
        None, description='dotted path to present_value field'
    )
    units: Optional[Any] = None
    states: Optional[Any] = None
