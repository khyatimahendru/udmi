"""Behavioral differential sequence alignment between test runs."""

import os
from typing import Any, Dict, List, Optional

from mantis.tools.artifacts import extract_timeline


def compare_test_runs(
    target_run: str,
    baseline_run: Optional[str] = None,
    udmi_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Performs behavioral differential sequence alignment between a target run and a reference baseline."""
    # Extract timelines
    target_timeline = extract_timeline(
        test_id=os.path.basename(target_run),
        device_id="target",
        run_dir=target_run,
        udmi_root=udmi_root,
    )

    baseline_timeline = None
    if baseline_run:
        baseline_timeline = extract_timeline(
            test_id=os.path.basename(baseline_run),
            device_id="baseline",
            run_dir=baseline_run,
            udmi_root=udmi_root,
        )

    # Standard checkpoints to align
    standard_checkpoints = [
        "TEST_START",
        "CONFIG_DISPATCH",
        "STAGE_WAIT_START",
        "STATE_CUTOFF_SET",
        "STATE_RECEIVED",
        "STALE_STATE_IGNORED",
        "JACKSON_DESERIALIZATION_FAILURE",
        "TIMEOUT_FAILURE",
        "TEST_RESULT",
    ]

    target_events = target_timeline.get("events", [])
    baseline_events = baseline_timeline.get("events", []) if baseline_timeline else []

    target_map = {e.get("checkpoint"): e for e in target_events if e.get("checkpoint")}
    baseline_map = {e.get("checkpoint"): e for e in baseline_events if e.get("checkpoint")}

    aligned_steps: List[Dict[str, Any]] = []
    divergence_found = False
    divergence_point = None

    # Step-by-step alignment
    step_num = 1
    for cp in standard_checkpoints:
        t_event = target_map.get(cp)
        b_event = baseline_map.get(cp)

        if not t_event and not b_event:
            continue

        b_desc = b_event.get("description", "(None - absent)") if b_event else "(Baseline: Pass expected)"
        t_desc = t_event.get("description", "(None)") if t_event else "(None)"

        delta = "Aligned"
        if cp in ("STALE_STATE_IGNORED", "JACKSON_DESERIALIZATION_FAILURE") and t_event and not b_event:
            if not divergence_found:
                delta = "DIVERGENCE POINT"
                divergence_found = True
                divergence_point = cp
            else:
                delta = "Cascading Failure"
        elif cp == "STATE_CUTOFF_SET" and t_event and b_event:
            # Check if cutoff differs
            t_cutoff = t_event.get("cutoff")
            b_cutoff = b_event.get("cutoff")
            if t_cutoff and b_cutoff and t_cutoff != b_cutoff:
                if not divergence_found:
                    delta = "DIVERGENCE POINT"
                    divergence_found = True
                    divergence_point = cp
        elif cp == "TIMEOUT_FAILURE" and t_event:
            delta = "Cascading Failure" if divergence_found else "DIVERGENCE POINT"
            if not divergence_found:
                divergence_found = True
                divergence_point = cp
        elif cp == "TEST_RESULT":
            delta = "Final Outcome"

        aligned_steps.append({
            "step": step_num,
            "checkpoint": cp,
            "baseline": b_desc,
            "target": t_desc,
            "delta": delta,
        })
        step_num += 1

    # Render formatted markdown differential table
    table_lines = [
        "| Step | Protocol Checkpoint | Baseline Run | Target Run | Delta |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for step in aligned_steps:
        table_lines.append(
            f"| {step['step']} | `{step['checkpoint']}` | {step['baseline']} | {step['target']} | **{step['delta']}** |"
        )
    diff_table_md = "\n".join(table_lines)

    return {
        "status": "SUCCESS",
        "target_run": target_run,
        "baseline_run": baseline_run,
        "divergence_point": divergence_point or ("TIMEOUT" if target_timeline.get("result") == "FAIL" else None),
        "target_result": target_timeline.get("result", "UNKNOWN"),
        "baseline_result": baseline_timeline.get("result", "PASS") if baseline_timeline else "PASS",
        "aligned_steps": aligned_steps,
        "differential_table": diff_table_md,
    }
