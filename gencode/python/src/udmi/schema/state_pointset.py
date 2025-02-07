# generated by datamodel-codegen:
#   filename:  state_pointset.json

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .entry import Entry
from .state_pointset_point import PointPointsetState


@dataclass
class PointsetState:
    """
    A set of points reporting telemetry data.
    """

    timestamp: Optional[str] = None
    version: Optional[str] = None
    state_etag: Optional[str] = None
    status: Optional[Entry] = None
    points: Optional[Dict[str, PointPointsetState]] = None
    upgraded_from: Optional[str] = None
