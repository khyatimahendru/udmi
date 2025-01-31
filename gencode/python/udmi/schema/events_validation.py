# generated by datamodel-codegen:
#   filename:  events_validation.json
#   timestamp: 2025-01-31T07:45:30+00:00

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .entry import Entry


class Pointset(BaseModel):
    """
    Errors specific to pointset handling
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    missing: Optional[List[str]] = Field(
        None, description='Missing points discovered while validating a device'
    )
    extra: Optional[List[str]] = Field(
        None, description='Extra points discovered while validating a device'
    )


class ValidationEvents(BaseModel):
    """
    Validation device result
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    timestamp: Optional[datetime] = Field(
        None,
        description='RFC 3339 UTC timestamp the validation event was generated',
        examples=['2019-01-17T14:02:29.364Z'],
    )
    version: Optional[str] = Field(None, description='Version of the UDMI schema')
    sub_folder: Optional[str] = Field(
        None, description='Subfolder of the validated message'
    )
    sub_type: Optional[str] = Field(
        None, description='Subtype of the validated message'
    )
    status: Optional[Entry] = None
    pointset: Optional[Pointset] = Field(
        None,
        description='Errors specific to pointset handling',
        title='Pointset Summary',
    )
    errors: Optional[List[Entry]] = Field(
        None, description='List of errors encountered while validating a device'
    )
