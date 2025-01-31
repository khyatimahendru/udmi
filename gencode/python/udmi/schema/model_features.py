# generated by datamodel-codegen:
#   filename:  model_features.json

from __future__ import annotations

from typing import Dict, Optional

from pydantic import Field, RootModel, constr

from .discovery_feature import FeatureDiscovery


class TestingModel(
    RootModel[Optional[Dict[constr(pattern=r'^[._a-zA-Z]+$'), FeatureDiscovery]]]
):
    model_config = ConfigDict(
        extra='forbid',
    )
    root: Optional[Dict[constr(pattern=r'^[._a-zA-Z]+$'), FeatureDiscovery]] = Field(
        None, description='Model of supported features', title='Testing Model'
    )
