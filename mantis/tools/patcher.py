"""Safe site model metadata patcher with dry-run diffs and automatic .bak backups."""

import difflib
import json
import os
import shutil
from typing import Any, Dict, Optional


def _get_udmi_root(udmi_root: Optional[str] = None) -> str:
    if udmi_root is not None:
        return os.path.abspath(udmi_root)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def deep_merge(target: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge updates dict into target dict."""
    for key, value in updates.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def patch_site_model(
    site_model: str,
    device_id: str,
    patch_data: Dict[str, Any],
    dry_run: bool = False,
    udmi_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Safely updates or fixes JSON keys in a device metadata.json file."""
    root = _get_udmi_root(udmi_root)
    site_path = os.path.abspath(os.path.join(root, site_model))
    if not os.path.isdir(site_path):
        site_path = os.path.abspath(site_model)

    if not os.path.isdir(site_path):
        return {
            "status": "ERROR",
            "error": f"Site model directory not found: {site_model}",
        }

    dev_clean = device_id.strip()
    metadata_file = os.path.join(site_path, "devices", dev_clean, "metadata.json")

    if not os.path.isfile(metadata_file):
        return {
            "status": "ERROR",
            "error": f"Device metadata file not found: {metadata_file}",
        }

    try:
        with open(metadata_file, "r", encoding="utf-8") as f:
            original_content = f.read()
            original_json = json.loads(original_content)
    except Exception as e:
        return {
            "status": "ERROR",
            "error": f"Failed to read or parse {metadata_file}: {e}",
        }

    # Deep copy original and apply patch
    updated_json = json.loads(json.dumps(original_json))
    deep_merge(updated_json, patch_data)

    new_content = json.dumps(updated_json, indent=2) + "\n"

    # Compute unified diff
    diff_lines = list(
        difflib.unified_diff(
            original_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{os.path.relpath(metadata_file, root)}",
            tofile=f"b/{os.path.relpath(metadata_file, root)}",
        )
    )
    diff_str = "".join(diff_lines)

    if dry_run:
        return {
            "status": "DRY_RUN",
            "site_model": site_path,
            "device_id": dev_clean,
            "file": metadata_file,
            "diff": diff_str,
            "applied": False,
        }

    backup_file = f"{metadata_file}.bak"
    try:
        shutil.copy2(metadata_file, backup_file)
        with open(metadata_file, "w", encoding="utf-8") as f:
            f.write(new_content)
    except Exception as e:
        return {
            "status": "ERROR",
            "error": f"Failed to write patch to {metadata_file}: {e}",
            "backup": backup_file,
        }

    return {
        "status": "PATCHED",
        "site_model": site_path,
        "device_id": dev_clean,
        "file": metadata_file,
        "backup": backup_file,
        "diff": diff_str,
        "applied": True,
    }
