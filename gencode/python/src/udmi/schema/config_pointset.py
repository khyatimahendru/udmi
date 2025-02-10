# generated by datamodel-codegen:
#   filename:  config_pointset.json

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .config_pointset_point import PointPointsetConfig


@dataclass
class PointsetConfig:
    """
    [Pointset Config Documentation](../docs/messages/pointset.md#config)
    """

    timestamp: Optional[str] = None
    version: Optional[str] = None
    state_etag: Optional[str] = None
    set_value_expiry: Optional[str] = None
    sample_limit_sec: Optional[int] = None
    sample_rate_sec: Optional[int] = None
    points: Optional[Dict[str, PointPointsetConfig]] = None
