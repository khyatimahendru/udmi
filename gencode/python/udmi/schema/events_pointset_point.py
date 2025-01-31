# generated by datamodel-codegen:
#   filename:  events_pointset_point.json
#   timestamp: 2025-01-31T07:45:30+00:00

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class PointPointsetEvents(BaseModel):
    """
    Object representation for for a single point
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    present_value: Optional[Any] = Field(
        None,
        description='The specific point data reading',
        examples=[24.1, 'running', 4],
    )
