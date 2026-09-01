"""Authoritative UDMI JSON Schema inspection and navigation."""

import json
import os
from typing import Any, Dict, List, Optional


def _get_udmi_root(udmi_root: Optional[str] = None) -> str:
    if udmi_root is not None:
        return os.path.abspath(udmi_root)
    # Default to repo root
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def list_udmi_schemas(udmi_root: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all available UDMI JSON schemas in the schema directory."""
    root = _get_udmi_root(udmi_root)
    schema_dir = os.path.join(root, "schema")
    if not os.path.isdir(schema_dir):
        return []

    schemas = []
    for filename in sorted(os.listdir(schema_dir)):
        if filename.endswith(".json"):
            filepath = os.path.join(schema_dir, filename)
            schema_info = {
                "name": filename[:-5],
                "filename": filename,
                "title": "",
                "description": "",
            }
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    schema_info["title"] = data.get("title", "")
                    schema_info["description"] = data.get("description", "")
            except Exception:
                pass
            schemas.append(schema_info)
    return schemas


def inspect_udmi_schema(
    schema_name: str,
    sub_path: Optional[str] = None,
    udmi_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieve authoritative JSON schema definitions for any UDMI message block."""
    root = _get_udmi_root(udmi_root)
    schema_dir = os.path.join(root, "schema")

    if not os.path.isdir(schema_dir):
        return {
            "status": "ERROR",
            "error": f"Schema directory not found: {schema_dir}",
        }

    clean_name = schema_name.strip()
    if clean_name.lower() in ("list", "*", "all"):
        all_schemas = list_udmi_schemas(root)
        return {
            "status": "SUCCESS",
            "schema_name": "list",
            "count": len(all_schemas),
            "schemas": all_schemas,
        }

    # Resolve filename
    target_file = clean_name if clean_name.endswith(".json") else f"{clean_name}.json"
    target_path = os.path.join(schema_dir, target_file)

    if not os.path.isfile(target_path):
        # Try finding partial / alternative matches
        candidates = [
            f for f in os.listdir(schema_dir)
            if f.endswith(".json") and (clean_name in f or f[:-5].endswith(clean_name))
        ]
        if candidates:
            # Pick closest match
            target_path = os.path.join(schema_dir, sorted(candidates)[0])
            target_file = sorted(candidates)[0]
        else:
            all_names = [f[:-5] for f in sorted(os.listdir(schema_dir)) if f.endswith(".json")]
            return {
                "status": "ERROR",
                "error": f"Schema '{schema_name}' not found in {schema_dir}",
                "available_schemas": all_names[:25],
            }

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {
            "status": "ERROR",
            "error": f"Failed to parse schema file {target_file}: {e}",
        }

    # Navigate sub_path if requested
    selected_data = data
    if sub_path:
        sub_keys = [k for k in sub_path.strip().split(".") if k]
        curr = data
        for k in sub_keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            elif isinstance(curr, dict) and "properties" in curr and k in curr["properties"]:
                curr = curr["properties"][k]
            else:
                return {
                    "status": "ERROR",
                    "schema_name": target_file[:-5],
                    "error": f"Sub-path '{sub_path}' (key '{k}') not found in schema.",
                    "available_properties": list(curr.keys()) if isinstance(curr, dict) else [],
                }
        selected_data = curr

    return {
        "status": "SUCCESS",
        "schema_name": target_file[:-5],
        "schema_file": target_path,
        "id": data.get("$id"),
        "title": data.get("title", target_file[:-5]),
        "description": data.get("description", ""),
        "required": data.get("required", []),
        "sub_path": sub_path,
        "schema": selected_data,
    }
