# generated by datamodel-codegen:
#   filename:  state_validation_sequence.json

from __future__ import annotations

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, constr

from .common import Stage
from .entry import Entry
from .state_validation_capability import CapabilityValidationState


class Result(Enum):
    start = 'start'
    errr = 'errr'
    skip = 'skip'
    pass_ = 'pass'
    fail = 'fail'


class Scoring(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    value: Optional[int] = None
    total: Optional[int] = None


class SequenceValidationState(BaseModel):
    """
    Sequence Validation State
    """

    model_config = ConfigDict(
        extra='forbid',
    )
    summary: Optional[str] = None
    stage: Optional[Stage] = None
    capabilities: Optional[
        Dict[constr(pattern=r'^[.a-z]+$'), CapabilityValidationState]
    ] = None
    result: Optional[Result] = Field(None, title='Sequence Result')
    status: Optional[Entry] = None
    scoring: Optional[Scoring] = None
