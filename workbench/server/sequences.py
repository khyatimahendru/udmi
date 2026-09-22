"""Sequence catalog discovery and stage gating (Layer 4).

The catalog is read from repository documentation rather than declared here,
so the Workbench always offers exactly the sequences this checkout can run.

Sources:
  * `docs/specs/sequences/generated.md` -> sequence name, feature stage, description
  * `etc/sequencer.out`                 -> feature bucket and reference result
"""

import os
import re
from typing import Any, Dict, List

from workbench.server.discovery import DiscoveryError
from workbench.server.runner import stages_admitted

SEQUENCE_HEADING_RE = re.compile(r"^##\s+([A-Za-z0-9_+]+)\s+\(([^)]+)\)")
RESULT_LINE_RE = re.compile(r"^RESULT\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s*(.*)$")


def _split_facet(raw_name: str) -> tuple:
    """Splits `scan_single_future+vendor` into ('scan_single_future', 'vendor').

    The `+facet` suffix is appended by SequenceBase.getTestName at result time
    and is NOT a JUnit method name. Only the base name is a valid sequencer
    target.
    """
    base, separator, facet = raw_name.partition("+")
    return base, (facet if separator else None)


def _read_reference_results(udmi_root: str) -> tuple:
    """Reads bucket/stage/reference metadata from the recorded sequencer run."""
    buckets: Dict[str, Dict[str, Any]] = {}
    facets: Dict[str, set] = {}

    results_path = os.path.join(udmi_root, "etc", "sequencer.out")
    if not os.path.isfile(results_path):
        return buckets, facets

    with open(results_path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = RESULT_LINE_RE.match(line.strip())
            if not match:
                continue
            result, bucket, raw_name, stage, score, message = match.groups()
            base_name, facet = _split_facet(raw_name)
            if facet:
                facets.setdefault(base_name, set()).add(facet)
            buckets.setdefault(base_name, {
                "bucket": bucket,
                "stage": stage,
                "reference_result": result,
                "reference_score": score,
                "reference_message": message.strip(),
            })
    return buckets, facets


def _first_description_line(lines: List[str], start: int) -> str:
    """Returns the prose line following a heading, skipping steps and verdicts."""
    for follow in lines[start:]:
        text = follow.strip()
        if text.startswith("##"):
            break
        if not text:
            continue
        if re.match(r"^(?:\d+\.|[*\-+])\s", text):
            break
        if re.match(r"^test\s+(?:passed|failed|skipped)\b", text, re.IGNORECASE):
            break
        return text
    return ""


def list_sequences(udmi_root: str) -> List[Dict[str, Any]]:
    """Discovers the full sequence catalog from repository documentation.

    Facet variants are folded into their base sequence rather than listed
    separately, because only base names can be passed to `bin/sequencer`.
    """
    buckets, facets = _read_reference_results(udmi_root)

    catalog_path = os.path.join(udmi_root, "docs", "specs", "sequences", "generated.md")
    if not os.path.isfile(catalog_path):
        raise DiscoveryError(
            f"Sequence catalog not found at {catalog_path}. "
            "Run 'bin/gencode_seq' to generate the sequence documentation."
        )

    with open(catalog_path, "r", encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    sequences: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}

    for idx, raw_line in enumerate(lines):
        match = SEQUENCE_HEADING_RE.match(raw_line.strip())
        if not match:
            continue
        raw_name, stage = match.group(1).strip(), match.group(2).strip()
        name, facet = _split_facet(raw_name)

        if facet:
            facets.setdefault(name, set()).add(facet)
        if name in seen:
            continue

        meta = buckets.get(name, {})
        entry = {
            "name": name,
            "stage": stage,
            "description": _first_description_line(lines, idx + 1),
            "bucket": meta.get("bucket"),
            "reference_result": meta.get("reference_result"),
            "reference_score": meta.get("reference_score"),
            "facets": [],
        }
        seen[name] = entry
        sequences.append(entry)

    # Sequences present in sequencer.out but absent from the generated catalog.
    for name, meta in sorted(buckets.items()):
        if name in seen:
            continue
        entry = {
            "name": name,
            "stage": meta.get("stage"),
            "description": meta.get("reference_message", ""),
            "bucket": meta.get("bucket"),
            "reference_result": meta.get("reference_result"),
            "reference_score": meta.get("reference_score"),
            "facets": [],
        }
        seen[name] = entry
        sequences.append(entry)

    for name, entry in seen.items():
        entry["facets"] = sorted(facets.get(name, ()))

    sequences.sort(key=lambda s: (s.get("bucket") or "zz", s["name"]))
    return sequences


def reject_stage_excluded(udmi_root: str, tests: List[str], min_stage: str) -> None:
    """Fails a run that names sequences the stage gate would silently skip.

    `bin/sequencer` defaults to min_stage=PREVIEW, and SequenceRunner only runs
    a test when its stage orders at or above that gate. Alpha-stage sequences
    (notably the `scan_*` discovery set) therefore produce no result at all
    rather than an error, which reads as "the test did not run" with no
    explanation.
    """
    if not tests:
        return

    admitted = set(stages_admitted(min_stage))
    catalog = {
        sequence["name"]: sequence.get("stage")
        for sequence in list_sequences(udmi_root)
    }

    excluded = {}
    for name in tests:
        stage = catalog.get(name.split("+")[0])
        if stage and stage.upper() not in admitted:
            excluded[name] = stage.upper()
    if not excluded:
        return

    needed = sorted({stage for stage in excluded.values()})
    remedy = "ALPHA" if "ALPHA" in needed else needed[0]
    listing = ", ".join(f"{name} ({stage})" for name, stage in sorted(excluded.items()))
    raise ValueError(
        f"{len(excluded)} selected sequence(s) are below the '{min_stage}' minimum stage "
        f"and would be skipped without reporting a result: {listing}. "
        f"Set min_stage to '{remedy}' to include them, or deselect them."
    )
