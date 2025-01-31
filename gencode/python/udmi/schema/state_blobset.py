# generated by datamodel-codegen:
#   filename:  state_blobset.json

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, constr

from .state_blobset_blob import BlobBlobsetState


class BlobsetState(BaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )
    blobs: Optional[
        Dict[constr(pattern=r'^_?[a-z][a-z0-9]*(_[a-z0-9]+)*$'), BlobBlobsetState]
    ] = None
