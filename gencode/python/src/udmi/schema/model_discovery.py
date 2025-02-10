# generated by datamodel-codegen:
#   filename:  model_discovery.json

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .model_discovery_family import FamilyDiscoveryModel


@dataclass
class DiscoveryModel:
    """
    Discovery target parameters
    """

    families: Optional[Dict[str, FamilyDiscoveryModel]] = None
