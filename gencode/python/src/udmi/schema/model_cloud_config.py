# generated by datamodel-codegen:
#   filename:  model_cloud_config.json

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class CloudConfigModel:
    """
    Information specific to how the device communicates with the cloud.
    """

    static_file: Optional[str] = None
