"""Real sequencer compliance and report downloads for UDMI Workbench (Layer 4).

Every number reported here is read out of an artifact that `bin/sequencer`
actually wrote. This module never infers, interpolates, or defaults a verdict:
a device that has not been tested is reported as untested, not as zero percent
compliant. Scoring an untested device as 0/0 would put a real-looking red row
in the compliance grid for a device nobody ever ran, which is the single most
damaging thing a certification view can do.

Compliance sources:
  * Structured results -> `<site_model>/out/sequencer_<device>.json`
  * Human report       -> `<site_model>/out/devices/<device>/results.md`
  * Raw result lines   -> `<site_model>/out/devices/<device>/RESULT.log`

The structured json is authoritative for counts and scores; the other two
files are download-only artifacts. Which of the three exist varies per device
in practice (a device can have a sequencer json with no markdown report, or a
RESULT.log with no json), so presence is probed per file rather than assumed
from a single marker.
"""

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from workbench.server.discovery import list_devices, resolve_site_model
from workbench.server.paths import display

# Matches artifacts.MAX_READ_BYTES. A report that exceeds it is refused rather
# than truncated: a half-sent RESULT.log looks like a short run instead of a
# failed download, and an operator would have no way to tell the difference.
MAX_REPORT_BYTES = 4 * 1024 * 1024

# The canonical result buckets. Anything the sequencer emits that is not one of
# these (`errr` for an aborted run, for example) is deliberately left unbucketed
# so it shows up as a discrepancy between `total` and pass+fail+skip instead of
# being quietly folded into one of them.
RESULT_BUCKETS = ("pass", "fail", "skip")

# kind -> (relative path template, download suffix, content type)
REPORT_KINDS: Dict[str, Tuple[str, str, str]] = {
    "results_md": (os.path.join("out", "devices", "{device}", "results.md"),
                   "results.md", "text/markdown"),
    "result_log": (os.path.join("out", "devices", "{device}", "RESULT.log"),
                   "RESULT.log", "text/plain"),
    "sequencer_json": (os.path.join("out", "sequencer_{device}.json"),
                       "sequencer.json", "application/json"),
}


class ComplianceError(Exception):
    """Raised when a site model, device, report kind, or report file is absent."""


def _validate_device_id(device_id: str, site_dir: str) -> str:
    """Proves `device_id` names a real device directory and cannot traverse.

    The device id is concatenated into artifact paths, so it is checked as a
    bare directory name before it is ever joined: a separator or `..` inside it
    would let a caller address files anywhere on disk through what looks like a
    device lookup. Existence is then confirmed against the site model's
    `devices/` directory, which is the only authoritative list of device ids.
    """
    if not device_id:
        raise ComplianceError("device_id parameter is required")
    if os.sep in device_id or "/" in device_id or "\\" in device_id or ".." in device_id:
        raise ComplianceError(
            f"Invalid device_id '{device_id}': must be a plain device name with no "
            "path separators or parent references."
        )

    device_dir = os.path.join(site_dir, "devices", device_id)
    if not os.path.isdir(device_dir):
        raise ComplianceError(f"Device '{device_id}' not found: {device_dir}")
    return device_id


def _sequencer_json_path(site_dir: str, device_id: str) -> str:
    return os.path.join(site_dir, "out", f"sequencer_{device_id}.json")


def _report_path(site_dir: str, device_id: str, kind: str) -> str:
    template = REPORT_KINDS[kind][0]
    return os.path.join(site_dir, template.format(device=device_id))


def _available_reports(site_dir: str, device_id: str) -> List[str]:
    """Lists the report kinds that are genuinely present for this device."""
    return [
        kind
        for kind in REPORT_KINDS
        if os.path.isfile(_report_path(site_dir, device_id, kind))
    ]


def _normalise_result(raw: Any) -> str:
    """Lowercases a sequencer verdict, leaving unrecognised verdicts intact.

    Case is the only thing normalised. An unexpected verdict is passed through
    verbatim so it reaches the UI as an unfamiliar value that demands attention,
    rather than being coerced into `fail` (which hides a broken run as a test
    failure) or `skip` (which hides it entirely).
    """
    if raw is None:
        return ""
    return str(raw).strip().lower()


def _scoring(entry: Dict[str, Any]) -> Dict[str, int]:
    scoring = entry.get("scoring") or {}
    return {
        "value": int(scoring.get("value") or 0),
        "total": int(scoring.get("total") or 0),
    }


def _parse_sequences(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flattens the feature -> sequences tree into one row per sequence.

    The compliance grid is a flat device x sequence matrix, but the sequencer
    writes sequences nested under their feature bucket. The feature is carried
    onto each row so grouping remains possible client-side without a second
    lookup.
    """
    rows: List[Dict[str, Any]] = []
    features = document.get("features") or {}
    for feature in sorted(features):
        sequences = (features[feature] or {}).get("sequences") or {}
        for name in sorted(sequences):
            entry = sequences[name] or {}
            status = entry.get("status") or {}
            rows.append({
                "name": name,
                "feature": feature,
                "result": _normalise_result(entry.get("result")),
                "stage": _normalise_result(entry.get("stage")),
                "score": _scoring(entry),
                "message": status.get("message"),
                "summary": entry.get("summary"),
                "timestamp": status.get("timestamp"),
            })
    return rows


def _empty_counts() -> Dict[str, int]:
    return {"pass": 0, "fail": 0, "skip": 0, "total": 0}


def _tally(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Returns (counts, score) summed over sequence rows."""
    counts = _empty_counts()
    score = {"value": 0, "total": 0}
    for row in rows:
        counts["total"] += 1
        if row["result"] in RESULT_BUCKETS:
            counts[row["result"]] += 1
        score["value"] += row["score"]["value"]
        score["total"] += row["score"]["total"]
    return counts, score


def _untested(device_id: str, reason: str, reports: List[str]) -> Dict[str, Any]:
    """Builds the record for a device with no usable structured results.

    `counts` and `score` are present but zero purely so the shape stays uniform
    for the caller; `has_results` is the field that decides whether they mean
    anything, and `reason` always names the concrete obstacle.
    """
    return {
        "device_id": device_id,
        "has_results": False,
        "reason": reason,
        "last_run": None,
        "udmi_version": None,
        "status_message": None,
        "counts": _empty_counts(),
        "score": {"value": 0, "total": 0},
        "sequences": [],
        "reports": reports,
    }


def _device_compliance(
    udmi_root: str, site_dir: str, device_id: str
) -> Dict[str, Any]:
    """Reads one device's compliance record, reporting absence as absence."""
    reports = _available_reports(site_dir, device_id)
    json_path = _sequencer_json_path(site_dir, device_id)

    if not os.path.isfile(json_path):
        return _untested(
            device_id,
            f"No sequencer results found at {display(json_path, udmi_root)}. "
            "Run bin/sequencer for this device to produce them.",
            reports,
        )

    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            document = json.load(fh)
    except json.JSONDecodeError as exc:
        # A corrupt results file is surfaced as "no trustworthy results" rather
        # than raised: one unreadable device must not blank out the whole site's
        # compliance view, but it must never be scored either.
        return _untested(
            device_id,
            f"Invalid sequencer results in {display(json_path, udmi_root)}: {exc}",
            reports,
        )
    except OSError as exc:
        return _untested(
            device_id,
            f"Cannot read {display(json_path, udmi_root)}: {exc}",
            reports,
        )

    if not isinstance(document, dict):
        return _untested(
            device_id,
            f"Invalid sequencer results in {display(json_path, udmi_root)}: "
            f"expected a JSON object, found {type(document).__name__}.",
            reports,
        )

    rows = _parse_sequences(document)
    counts, score = _tally(rows)
    status = document.get("status") or {}

    return {
        "device_id": device_id,
        "has_results": True,
        "reason": None,
        "last_run": document.get("timestamp"),
        "udmi_version": document.get("udmi_version"),
        "status_message": status.get("message"),
        "counts": counts,
        "score": score,
        "sequences": rows,
        "reports": reports,
    }


def site_compliance(udmi_root: str, site_model: str) -> Dict[str, Any]:
    """Builds the compliance matrix for every device in a site model.

    Every device that discovery finds appears in the result, tested or not.
    Omitting untested devices would make a site look fully covered when only a
    subset was ever run, so absence is reported explicitly and counted in
    `totals.devices` while being excluded from `totals.devices_with_results`.
    """
    site_dir = resolve_site_model(udmi_root, site_model)

    devices: List[Dict[str, Any]] = []
    totals = {"devices": 0, "devices_with_results": 0, "pass": 0, "fail": 0,
              "skip": 0, "total": 0}

    for device in list_devices(udmi_root, site_model):
        record = _device_compliance(udmi_root, site_dir, device["device_id"])
        devices.append(record)

        totals["devices"] += 1
        if record["has_results"]:
            totals["devices_with_results"] += 1
        for bucket in (*RESULT_BUCKETS, "total"):
            totals[bucket] += record["counts"][bucket]

    return {"site_model": site_model, "devices": devices, "totals": totals}


def device_report(
    udmi_root: str, site_model: str, device_id: str, kind: str
) -> Dict[str, Any]:
    """Reads one downloadable sequencer report for a device.

    Bytes are returned rather than text: `content_type` already states how the
    payload should be interpreted, and re-encoding a report on the way out would
    let this module alter a file an operator may be attaching to a certification
    submission.
    """
    if kind not in REPORT_KINDS:
        raise ComplianceError(
            f"Unknown report kind '{kind}'. Valid kinds: "
            f"{', '.join(sorted(REPORT_KINDS))}."
        )

    site_dir = resolve_site_model(udmi_root, site_model)
    _validate_device_id(device_id, site_dir)

    _, suffix, content_type = REPORT_KINDS[kind]
    target = _report_path(site_dir, device_id, kind)
    if not os.path.isfile(target):
        raise ComplianceError(
            f"No '{kind}' report for device '{device_id}': {display(target, udmi_root)} "
            "does not exist."
        )

    size = os.path.getsize(target)
    if size > MAX_REPORT_BYTES:
        raise ComplianceError(
            f"Report {display(target, udmi_root)} is {size} bytes, exceeding the "
            f"{MAX_REPORT_BYTES} byte download limit."
        )

    with open(target, "rb") as fh:
        content = fh.read()

    return {
        "filename": f"{device_id}_{suffix}",
        "content_type": content_type,
        "content": content,
        "size": size,
        "path": display(target, udmi_root),
    }
