"""Multi-path artifact discovery, log slicing, timeline extraction, and bundle ingestion."""

import json
import os
import re
import shutil
import tarfile
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mantis.tools.site_models import sanitize_credentials


def _get_udmi_root(udmi_root: Optional[str] = None) -> str:
    if udmi_root is not None:
        return os.path.abspath(udmi_root)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def discover_test_runs(
    base_dir: Optional[str] = None,
    udmi_root: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Discover available test run directories and log artifacts."""
    root = _get_udmi_root(udmi_root)
    search_dirs = []
    if base_dir:
        search_dirs.append(os.path.abspath(base_dir))
    else:
        search_dirs.extend([
            os.path.join(root, "out", "runs"),
            os.path.join(root, "out"),
            os.path.join(root, "var", "instances"),
        ])

    runs = []
    for sdir in search_dirs:
        if not os.path.isdir(sdir):
            continue
        for entry in sorted(os.listdir(sdir)):
            full_path = os.path.join(sdir, entry)
            if os.path.isdir(full_path):
                # Check for log files
                log_files = [f for f in os.listdir(full_path) if f.endswith(".log") or f.endswith(".out")]
                if log_files or os.path.isfile(os.path.join(full_path, "session_info.json")):
                    runs.append({
                        "run_id": entry,
                        "path": full_path,
                        "logs": log_files,
                    })
    return runs


def extract_log_slice(
    log_file: str,
    test_id: Optional[str] = None,
    start_pattern: Optional[str] = None,
    end_pattern: Optional[str] = None,
    max_lines: int = 1000,
) -> List[str]:
    """Slice raw log content to lines matching test execution bounds."""
    if not os.path.isfile(log_file):
        return []

    lines = []
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except Exception:
        return []

    in_slice = (test_id is None and start_pattern is None)
    for line in all_lines:
        line_str = line.rstrip("\n")
        if not in_slice:
            if test_id and test_id in line_str and ("Starting test" in line_str or "start_test" in line_str):
                in_slice = True
            elif start_pattern and re.search(start_pattern, line_str):
                in_slice = True

        if in_slice:
            lines.append(line_str)
            if len(lines) >= max_lines:
                break
            if test_id and test_id in line_str and ("RESULT:" in line_str or "terminating_test" in line_str or "finished test" in line_str):
                break
            elif end_pattern and re.search(end_pattern, line_str):
                break

    if not lines and all_lines:
        # Fallback to last max_lines if no explicit slice bounds were found
        lines = [l.rstrip("\n") for l in all_lines[-max_lines:]]

    return lines


def _extract_multiline_block(raw_lines: List[str], start_idx: int, max_lines: int = 15) -> str:
    """Extract a multi-line Java exception stack trace, Caused by block, or structured error output."""
    if start_idx >= len(raw_lines):
        return ""
    
    block = [raw_lines[start_idx].rstrip("\r\n")]
    for j in range(start_idx + 1, min(len(raw_lines), start_idx + max_lines)):
        line = raw_lines[j].rstrip("\r\n")
        stripped = line.strip()
        if not stripped:
            break
        # Lines that belong to stack traces, causes, references, or source locations
        if (
            line.startswith("\t")
            or line.startswith("  ")
            or stripped.startswith("at ")
            or stripped.startswith("Caused by:")
            or stripped.startswith("... ")
            or "line:" in stripped.lower()
            or "column:" in stripped.lower()
            or "(through reference chain:" in stripped
            or "expected" in stripped.lower()
            or "schema validation" in stripped.lower()
        ):
            block.append(stripped)
            if "Starting test" in stripped or "RESULT:" in stripped:
                break
        else:
            break
    return "\n".join(block)


def extract_timeline(
    test_id: str,
    device_id: str,
    run_dir: Optional[str] = None,
    udmi_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Deterministically extracts chronological timestamps, transactions (RC:...), cutoffs, and multi-line status transitions."""
    root = _get_udmi_root(udmi_root)

    # Locate run directory
    target_dir = None
    if run_dir and os.path.isdir(run_dir):
        target_dir = os.path.abspath(run_dir)
    else:
        # Search candidate locations
        candidates = [
            os.path.join(root, "out", "runs", f"{device_id}_{test_id}"),
            os.path.join(root, "out", "runs", test_id),
            os.path.join(root, "out", test_id),
            os.path.join(root, "out"),
        ]
        # Also check var/instances/
        instances_dir = os.path.join(root, "var", "instances")
        if os.path.isdir(instances_dir):
            for inst in os.listdir(instances_dir):
                inst_path = os.path.join(instances_dir, inst)
                candidates.extend([
                    os.path.join(inst_path, "out"),
                    inst_path,
                ])

        for c in candidates:
            if os.path.isdir(c):
                target_dir = c
                break

    if not target_dir:
        target_dir = os.path.join(root, "out")

    events: List[Dict[str, Any]] = []
    transactions: List[str] = []
    cutoff_threshold: Optional[str] = None
    stale_state_detected = False
    stale_state_timestamp: Optional[str] = None
    jackson_error: Optional[str] = None
    timeout_error: Optional[str] = None
    pointset_timestamps: List[str] = []
    result_status = "UNKNOWN"

    transport_error: Optional[str] = None
    auth_error: Optional[str] = None
    schema_error: Optional[str] = None

    log_files = {
        "sequence": os.path.join(target_dir, "sequence.log"),
        "pubber": os.path.join(target_dir, "pubber.log"),
        "device_system": os.path.join(target_dir, "device_system.log"),
        "udmis": os.path.join(target_dir, "udmis.log"),
        "validator": os.path.join(target_dir, "validator.log"),
    }

    # Regex patterns
    rc_pattern = re.compile(r"RC:([a-f0-9]+(?:\.[0-9]+)?)")
    cutoff_pattern = re.compile(r"(?:Cutoff set:|Setting (?:state )?cutoff to|cutoff threshold is)\s*([0-9T:\-\.Z]+)", re.IGNORECASE)
    stale_pattern = re.compile(r"ignoring stale state update(?:\s+timestamp\s+)?([0-9T:\-\.Z]+)?", re.IGNORECASE)
    jackson_pattern = re.compile(r"(?:UnrecognizedPropertyException|JsonParseException|JsonMappingException|MismatchedInputException|Cannot deserialize|Jackson error|InvalidFormatException)", re.IGNORECASE)
    timeout_pattern = re.compile(r"(?:Stage timeout after|Timeout waiting for|timed out after|TimeoutException|AssertionError:\s*Sequence failed)", re.IGNORECASE)
    transport_pattern = re.compile(r"(?:ConnectionRefusedError|ConnectException|SSLHandshakeException|SSL_ERROR|Connection refused(?!:\s*not author)|Broker unreachable|MqttException)", re.IGNORECASE)
    auth_pattern = re.compile(r"(?:Bad username or password|Not authorized to connect|Connection Refused:\s*not authorised|Authentication failure|NotAuthorizedException)", re.IGNORECASE)
    schema_pattern = re.compile(r"(?:Schema validation error|missing required (?:point|property)|point not defined in model|Pointset schema violation)", re.IGNORECASE)
    ts_pattern = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z?)")

    step_idx = 1

    for log_name, log_path in log_files.items():
        if not os.path.isfile(log_path):
            continue

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.readlines()

        for line_no, raw_line in enumerate(raw_lines, 1):
            line = raw_line.strip()
            if not line:
                continue

            # Look for timestamps in line
            ts_match = ts_pattern.search(line)
            line_ts = ts_match.group(1) if ts_match else None

            # Look for transactions
            for m in rc_pattern.finditer(line):
                rc_id = f"RC:{m.group(1)}"
                if rc_id not in transactions:
                    transactions.append(rc_id)

            # Check for test start
            if ("Starting test" in line or "start_test" in line) and test_id in line:
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "TEST_START",
                    "timestamp": line_ts,
                    "description": f"Starting test {test_id} for {device_id}",
                })
                step_idx += 1

            # Check for config dispatch
            if "Dispatched config" in line or "Publishing config" in line or "Sending config" in line:
                m = rc_pattern.search(line)
                rc_str = f" ({m.group(0)})" if m else ""
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "CONFIG_DISPATCH",
                    "timestamp": line_ts,
                    "description": f"Dispatched config update{rc_str}",
                })
                step_idx += 1

            # Check for state cutoff
            c_match = cutoff_pattern.search(line)
            if c_match:
                cutoff_threshold = c_match.group(1)
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "STATE_CUTOFF_SET",
                    "timestamp": line_ts,
                    "cutoff": cutoff_threshold,
                    "description": f"Sequencer cutoff set to {cutoff_threshold}",
                })
                step_idx += 1

            # Check for state received
            if "Received state" in line or "Handling device state" in line:
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "STATE_RECEIVED",
                    "timestamp": line_ts,
                    "description": f"Received device state update",
                })
                step_idx += 1

            # Check for stale state
            if stale_pattern.search(line) or "stale state" in line.lower():
                stale_state_detected = True
                s_match = stale_pattern.search(line)
                if s_match and s_match.group(1):
                    stale_state_timestamp = s_match.group(1)
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "STALE_STATE_IGNORED",
                    "timestamp": line_ts,
                    "description": "Sequencer ignored stale state update (lagging cutoff)",
                })
                step_idx += 1

            # Check for Jackson parse error (including multi-line / Caused by)
            if (jackson_pattern.search(line) or "caused by: com.fasterxml.jackson" in line.lower()) and not jackson_error:
                jackson_block = _extract_multiline_block(raw_lines, line_no - 1)
                jackson_error = jackson_block or line
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "JACKSON_DESERIALIZATION_FAILURE",
                    "timestamp": line_ts,
                    "description": f"Jackson parser error: {line[:80]}",
                })
                step_idx += 1

            # Check for timeout error
            if timeout_pattern.search(line) and not timeout_error:
                timeout_block = _extract_multiline_block(raw_lines, line_no - 1, max_lines=6)
                timeout_error = timeout_block or line
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "TIMEOUT_FAILURE",
                    "timestamp": line_ts,
                    "description": f"Timeout failure: {line[:80]}",
                })
                step_idx += 1

            # Check for transport error
            if transport_pattern.search(line) and not transport_error:
                tr_block = _extract_multiline_block(raw_lines, line_no - 1, max_lines=6)
                transport_error = tr_block or line
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "TRANSPORT_FAILURE",
                    "timestamp": line_ts,
                    "description": f"Transport failure: {line[:80]}",
                })
                step_idx += 1

            # Check for auth error
            if auth_pattern.search(line) and not auth_error:
                auth_block = _extract_multiline_block(raw_lines, line_no - 1, max_lines=6)
                auth_error = auth_block or line
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "AUTH_FAILURE",
                    "timestamp": line_ts,
                    "description": f"Authentication failure: {line[:80]}",
                })
                step_idx += 1

            # Check for schema error
            if schema_pattern.search(line) and not schema_error:
                schema_block = _extract_multiline_block(raw_lines, line_no - 1, max_lines=6)
                schema_error = schema_block or line
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "SCHEMA_VALIDATION_FAILURE",
                    "timestamp": line_ts,
                    "description": f"Schema validation error: {line[:80]}",
                })
                step_idx += 1

            # Check for pointset events (for cadence calculation)
            if "events/pointset" in line or "events_pointset" in line or "pointset telemetry" in line.lower():
                if line_ts:
                    pointset_timestamps.append(line_ts)

            # Check for test result
            if "RESULT: PASS" in line or "result: pass" in line.lower() or "Test passed" in line:
                result_status = "PASS"
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "TEST_RESULT",
                    "timestamp": line_ts,
                    "status": "PASS",
                    "description": "RESULT: PASS",
                })
                step_idx += 1
            elif "RESULT: FAIL" in line or "result: fail" in line.lower() or "Test failed" in line:
                result_status = "FAIL"
                events.append({
                    "step": step_idx,
                    "source": log_name,
                    "line": line_no,
                    "checkpoint": "TEST_RESULT",
                    "timestamp": line_ts,
                    "status": "FAIL",
                    "description": "RESULT: FAIL",
                })
                step_idx += 1

    # Cadence calculation
    avg_sample_rate_sec = None
    if len(pointset_timestamps) >= 2:
        try:
            parsed_ts = []
            for t in pointset_timestamps:
                clean_t = t.rstrip("Z")
                dt = datetime.fromisoformat(clean_t)
                parsed_ts.append(dt)
            deltas = [(parsed_ts[i+1] - parsed_ts[i]).total_seconds() for i in range(len(parsed_ts)-1)]
            if deltas:
                avg_sample_rate_sec = sum(deltas) / len(deltas)
        except Exception:
            pass

    return {
        "status": "SUCCESS",
        "test_id": test_id,
        "device_id": device_id,
        "run_dir": target_dir,
        "result": result_status,
        "transactions": transactions,
        "cutoff_threshold": cutoff_threshold,
        "stale_state_detected": stale_state_detected,
        "stale_state_timestamp": stale_state_timestamp,
        "jackson_error": jackson_error,
        "timeout_error": timeout_error,
        "transport_error": transport_error,
        "auth_error": auth_error,
        "schema_error": schema_error,
        "avg_sample_rate_sec": avg_sample_rate_sec,
        "events": events,
    }


def ingest_support_bundle(
    bundle_path: str,
    extract_to: Optional[str] = None,
    udmi_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Ingests a support bundle zip or tarball, extracts manifest and logs, and redacts credentials."""
    root = _get_udmi_root(udmi_root)
    bundle_file = os.path.abspath(bundle_path)
    if not os.path.isfile(bundle_file):
        return {
            "status": "ERROR",
            "error": f"Support bundle file not found: {bundle_path}",
        }

    if extract_to is None:
        extract_to = os.path.join(root, "out", "extracted_bundles", os.path.basename(bundle_file).replace(".", "_"))
    os.makedirs(extract_to, exist_ok=True)

    # Extract
    if zipfile.is_zipfile(bundle_file):
        with zipfile.ZipFile(bundle_file, "r") as z:
            z.extractall(extract_to)
    elif tarfile.is_tarfile(bundle_file):
        with tarfile.open(bundle_file, "r:*") as t:
            t.extractall(extract_to)
    else:
        return {
            "status": "ERROR",
            "error": f"Unsupported bundle format for {bundle_file}. Expected .zip, .tar.gz, or .tgz",
        }

    # Search for triage_manifest.json
    manifest = {}
    manifest_file = os.path.join(extract_to, "triage_manifest.json")
    if not os.path.isfile(manifest_file):
        # Check subdirectories
        for r, _, files in os.walk(extract_to):
            if "triage_manifest.json" in files:
                manifest_file = os.path.join(r, "triage_manifest.json")
                break

    if os.path.isfile(manifest_file):
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = sanitize_credentials(json.load(f))
        except Exception as e:
            manifest = {"error": f"Failed to parse triage_manifest.json: {e}"}

    # Find logs directory
    logs_found = []
    for r, _, files in os.walk(extract_to):
        for f in files:
            if f.endswith(".log") or f.endswith(".out"):
                logs_found.append(os.path.relpath(os.path.join(r, f), extract_to))

    return {
        "status": "SUCCESS",
        "bundle_file": bundle_file,
        "extracted_dir": extract_to,
        "manifest": manifest,
        "logs": logs_found,
    }
