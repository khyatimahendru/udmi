from typing import Any, Dict
from dataclasses import dataclass
from dataclasses_json import DataClassJsonMixin


def _remove_none(obj: Any) -> Any:
  if isinstance(obj, dict):
    return {k: _remove_none(v) for k, v in obj.items() if v is not None}
  if isinstance(obj, list):
    return [_remove_none(v) for v in obj if v is not None]
  return obj


@dataclass
class DataModel(DataClassJsonMixin):
  """Base class for all generated UDMI models."""

  def to_dict(self, encode_json: bool = False) -> Dict[str, Any]:
    raw_dict = super().to_dict(encode_json=encode_json)
    return _remove_none(raw_dict)



