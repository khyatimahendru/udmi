# generated by datamodel-codegen:
#   filename:  state_localnet_family.json

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .entry import Entry


@dataclass
class FamilyLocalnetState:
    addr: Optional[str] = None
    status: Optional[Entry] = None
