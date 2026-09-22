"""Real Repository Discovery for UDMI Workbench (Layer 4).

Every value returned by this module is discovered from the actual UDMI
repository and from site models on disk. This module contains NO fabricated
devices, tests, results, scores, or statuses. If a resource is missing, it
fails explicitly rather than substituting a placeholder.

Discovery sources:
  * Site models   -> `sites/*/cloud_iot_config.json` plus any registered root
  * Devices       -> `<site_model>/devices/*/metadata.json`
  * Test results  -> `<site_model>/out/devices/<device>/tests/<test>/`

Site models are frequently kept outside the UDMI checkout, so every function
here accepts an absolute site model path as readily as a repository-relative
one. Which external directories may be scanned is decided by the site-root
registry, not by this module.
"""

from datetime import datetime, timezone
import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional

from workbench.server.paths import absolute, display, is_within

SITE_CONFIG_FILENAME = "cloud_iot_config.json"


class DiscoveryError(Exception):
    """Raised when a requested repository resource does not exist."""


def _require_dir(path: str, label: str) -> str:
    if not os.path.isdir(path):
        raise DiscoveryError(f"{label} not found: {path}")
    return path


def resolve_site_model(udmi_root: str, site_model: str) -> str:
    """Resolves a site model reference to an absolute directory, or fails."""
    if not site_model:
        raise DiscoveryError("site_model parameter is required")
    candidate = absolute(udmi_root, site_model)
    _require_dir(candidate, "Site model directory")
    if not os.path.isfile(os.path.join(candidate, SITE_CONFIG_FILENAME)):
        nested = os.path.join(candidate, "udmi")
        if os.path.isdir(nested) and os.path.isfile(os.path.join(nested, SITE_CONFIG_FILENAME)):
            return nested
    return candidate


def describe_site_model(site_dir: str, udmi_root: str) -> Dict[str, Any]:
    """Builds a site model descriptor from its on-disk cloud_iot_config.json.

    Supports both direct layout (<site_model>/cloud_iot_config.json) and
    nested layout (<site_model>/udmi/cloud_iot_config.json). If the directory
    is named 'udmi', the site model name is derived from its parent folder.
    """
    config_path = os.path.join(site_dir, SITE_CONFIG_FILENAME)
    target_dir = site_dir
    if not os.path.isfile(config_path):
        nested = os.path.join(site_dir, "udmi")
        if os.path.isdir(nested) and os.path.isfile(os.path.join(nested, SITE_CONFIG_FILENAME)):
            target_dir = nested
            config_path = os.path.join(target_dir, SITE_CONFIG_FILENAME)
        else:
            raise DiscoveryError(
                f"'{site_dir}' is not a site model: no {SITE_CONFIG_FILENAME} found."
            )

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"Invalid {SITE_CONFIG_FILENAME} in '{target_dir}': {exc}") from exc

    devices_dir = os.path.join(target_dir, "devices")
    device_count = (
        len([d for d in os.listdir(devices_dir) if os.path.isdir(os.path.join(devices_dir, d))])
        if os.path.isdir(devices_dir)
        else 0
    )

    site_real = os.path.realpath(target_dir)
    base_name = os.path.basename(site_real)
    if base_name == "udmi":
        parent_dir = os.path.dirname(site_real)
        name = os.path.basename(parent_dir) or base_name
    else:
        name = base_name

    return {
        "path": display(target_dir, udmi_root),
        "absolute_path": site_real,
        "name": name,
        "site_name": config.get("site_name"),
        "registry_id": config.get("registry_id"),
        "iot_provider": config.get("iot_provider"),
        "project_id": config.get("project_id"),
        "device_count": device_count,
        "external": not is_within(target_dir, udmi_root),
    }


def scan_for_site_models(root_dir: str, udmi_root: str) -> List[Dict[str, Any]]:
    """Finds site models at `root_dir` and in its immediate subdirectories.

    Supports direct layout and nested `udmi/` layout. A directory an operator
    points at is either a site model itself or a folder holding several of
    them.
    """
    try:
        entries = sorted(os.listdir(root_dir))
    except OSError as exc:
        raise DiscoveryError(f"Cannot read directory '{root_dir}': {exc}") from exc

    is_direct = os.path.isfile(os.path.join(root_dir, SITE_CONFIG_FILENAME))
    is_nested = (not is_direct) and os.path.isfile(
        os.path.join(root_dir, "udmi", SITE_CONFIG_FILENAME)
    )
    if is_direct or is_nested:
        target = os.path.join(root_dir, "udmi") if is_nested else root_dir
        return [describe_site_model(target, udmi_root)]

    models: List[Dict[str, Any]] = []
    seen: set = set()
    for name in entries:
        if name.startswith("."):
            continue
        child = os.path.join(root_dir, name)
        if not os.path.isdir(child):
            continue
        target = None
        if os.path.isfile(os.path.join(child, SITE_CONFIG_FILENAME)):
            target = child
        elif os.path.isfile(os.path.join(child, "udmi", SITE_CONFIG_FILENAME)):
            target = os.path.join(child, "udmi")
        if target:
            desc = describe_site_model(target, udmi_root)
            if desc["absolute_path"] not in seen:
                seen.add(desc["absolute_path"])
                models.append(desc)
    return models


def list_site_models(udmi_root: str, extra_roots: Iterable[str] = ()) -> Dict[str, Any]:
    """Discovers site models in `sites/` and in every registered search root.

    A registered root that has gone away (an unmounted drive, a renamed
    directory) is reported in `unavailable_roots` instead of being dropped, so
    a vanished path is visible in the UI rather than silently producing a
    shorter list.
    """
    sites_root = os.path.join(udmi_root, "sites")
    if not os.path.isdir(sites_root):
        raise DiscoveryError(f"No sites/ directory found under {udmi_root}")

    models: List[Dict[str, Any]] = []
    unavailable: List[Dict[str, str]] = []
    seen: set = set()

    def collect(directory: str, source: str) -> None:
        for model in scan_for_site_models(directory, udmi_root):
            if model["absolute_path"] in seen:
                continue
            seen.add(model["absolute_path"])
            model["source"] = source
            models.append(model)

    collect(sites_root, "repository")

    for root in extra_roots:
        if not os.path.isdir(root):
            unavailable.append({
                "path": root,
                "reason": "Registered path is no longer a readable directory.",
            })
            continue
        collect(root, root)

    models.sort(key=lambda model: (model["source"] != "repository", model["name"]))
    return {"site_models": models, "unavailable_roots": unavailable}


def list_devices(udmi_root: str, site_model: str) -> List[Dict[str, Any]]:
    """Discovers all devices and their real metadata within a site model."""
    site_dir = resolve_site_model(udmi_root, site_model)
    devices_dir = _require_dir(os.path.join(site_dir, "devices"), "Devices directory")

    devices: List[Dict[str, Any]] = []
    for device_id in sorted(os.listdir(devices_dir)):
        device_path = os.path.join(devices_dir, device_id)
        if not os.path.isdir(device_path):
            continue

        metadata: Dict[str, Any] = {}
        metadata_path = os.path.join(device_path, "metadata.json")
        if os.path.isfile(metadata_path):
            try:
                with open(metadata_path, "r", encoding="utf-8") as fh:
                    metadata = json.load(fh)
            except json.JSONDecodeError as exc:
                devices.append({
                    "device_id": device_id,
                    "error": f"Invalid metadata.json: {exc}",
                })
                continue

        system = metadata.get("system") or {}
        hardware = system.get("hardware") or {}
        gateway = metadata.get("gateway") or {}
        points = (metadata.get("pointset") or {}).get("points") or {}

        devices.append({
            "device_id": device_id,
            "make": hardware.get("make"),
            "model": hardware.get("model"),
            "software": system.get("software"),
            "description": system.get("description"),
            "is_gateway": bool(gateway.get("proxy_ids")),
            "proxy_ids": gateway.get("proxy_ids") or [],
            "gateway_id": gateway.get("gateway_id"),
            "point_count": len(points),
            "points": sorted(points.keys()),
            "has_metadata": os.path.isfile(metadata_path),
        })
    return devices


def get_device_metadata(udmi_root: str, site_model: str, device_id: str) -> Dict[str, Any]:
    """Returns the complete raw metadata.json for a single device."""
    site_dir = resolve_site_model(udmi_root, site_model)
    metadata_path = os.path.join(site_dir, "devices", device_id, "metadata.json")
    if not os.path.isfile(metadata_path):
        raise DiscoveryError(f"No metadata.json for device '{device_id}' in {site_model}")
    with open(metadata_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _classify_result(test_dir: str) -> Dict[str, Any]:
    """Determines real pass/skip/fail status from on-disk sequence artifacts."""
    sequence_md = os.path.join(test_dir, "sequence.md")
    sequence_log = os.path.join(test_dir, "sequence.log")

    status = "unknown"
    summary = ""
    if os.path.isfile(sequence_md):
        with open(sequence_md, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        lowered = content.lower()
        verdict = re.search(r"^test\s+(passed|failed|skipped)\b(.*)$", content, re.IGNORECASE | re.MULTILINE)
        if verdict:
            status = {"passed": "pass", "failed": "fail", "skipped": "skip"}[verdict.group(1).lower()]
            summary = verdict.group(2).strip(" .:-")
        elif "sequence complete" in lowered:
            status = "pass"
        elif os.path.isfile(sequence_log):
            status = "fail"
    elif os.path.isfile(sequence_log):
        status = "fail"

    return {"status": status, "summary": summary}


def _extract_project_spec(test_dir: str) -> Optional[str]:
    """Reads the authoritative projectId recorded in captured .attr files."""
    try:
        attr_files = sorted(
            (f for f in os.listdir(test_dir) if f.endswith(".attr")),
            key=lambda x: (0 if "validation" in x else 1 if "system" in x else 2),
        )
    except OSError:
        return None

    for attr_file in attr_files:
        try:
            with open(os.path.join(test_dir, attr_file), "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        project_id = data.get("projectId")
        if project_id:
            return project_id
    return None


def get_device_results(udmi_root: str, site_model: str, device_id: str) -> Dict[str, Any]:
    """Reads real recorded sequencer results for a device from disk."""
    site_dir = resolve_site_model(udmi_root, site_model)
    tests_dir = os.path.join(site_dir, "out", "devices", device_id, "tests")

    results: Dict[str, Any] = {}
    if os.path.isdir(tests_dir):
        for test_name in sorted(os.listdir(tests_dir)):
            test_dir = os.path.join(tests_dir, test_name)
            if not os.path.isdir(test_dir):
                continue

            mtime = os.path.getmtime(test_dir)
            artifacts = []
            for artifact in sorted(os.listdir(test_dir)):
                artifact_path = os.path.join(test_dir, artifact)
                if os.path.isfile(artifact_path):
                    artifacts.append(artifact)
                    mtime = max(mtime, os.path.getmtime(artifact_path))

            classification = _classify_result(test_dir)
            results[test_name] = {
                "status": classification["status"],
                "summary": classification["summary"],
                "timestamp": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "project_spec": _extract_project_spec(test_dir),
                "artifacts": artifacts,
                "artifact_dir": display(test_dir, udmi_root),
            }

    return {
        "site_model": site_model,
        "device_id": device_id,
        "results_dir": display(tests_dir, udmi_root),
        "results_dir_exists": os.path.isdir(tests_dir),
        "results": results,
    }
