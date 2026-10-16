"""gencode/python/udmi/schema/_base.py"""
from dataclasses import dataclass
from typing import Any, Dict
from dataclasses_json import DataClassJsonMixin


def _strip_none(value: Any) -> Any:
  """Recursively removes keys with None values from dictionaries."""
  if isinstance(value, dict):
    return {k: _strip_none(v) for k, v in value.items() if v is not None}
  if isinstance(value, list):
    return [_strip_none(v) for v in value]
  return value


@dataclass
class DataModel(DataClassJsonMixin):
  """Base class for all generated UDMI models."""

  def to_dict(self, encode_json: bool = False) -> Dict[str, Any]:
    return _strip_none(super().to_dict(encode_json=encode_json))

