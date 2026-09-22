"""Tests for the Workbench compliance module.

The point of the module is that it never invents a result, so these tests pin
genuinely recorded verdicts rather than accepting any well-shaped payload.

Site-wide invariants (every device appears, reports list only files that exist,
totals aggregate) are asserted against the real `sites/udmi_site_model`, since
those hold whatever has been run. The verdict-level assertions instead use
`RECORDED_RUN` below, a run captured verbatim from that same site model. They
used to read the working tree directly, which meant the suite started failing
the moment an operator ran a sequencer -- the recorded verdict is not a fixed
property of the repository, it is whatever was run last.

Synthetic site models cover the cases the repository cannot provide: a device
with no sequencer json, and a device whose sequencer json is corrupt.
"""

import json
import os

import pytest

from workbench.server import compliance, discovery
from workbench.server.compliance import ComplianceError

SITE_MODEL = "sites/udmi_site_model"
UDMI_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)

#: A real `bin/sequencer` run against AHU-1, captured verbatim from
#: `sites/udmi_site_model/out/sequencer_AHU-1.json`. Held here so the verdict
#: assertions below survive later runs against that site model.
RECORDED_RUN = {
    "cloud_version": {
        "deployed_at": "2026-09-21T10:59:17Z",
        "deployed_by": "giraffe@safari.com",
        "functions_max": 18,
        "functions_min": 18,
        "udmi_ref": "g123456789",
        "udmi_version": "1.4.1",
    },
    "features": {
        "system": {
            "sequences": {
                "broken_config": {
                    "capabilities": {},
                    "result": "fail",
                    "scoring": {"total": 8, "value": 0},
                    "stage": "stable",
                    "status": {
                        "category": "validation.feature.sequence",
                        "level": 500,
                        "message": "Timeout waiting for initial device state",
                        "timestamp": "2026-09-21T15:40:16Z",
                    },
                    "summary": (
                        "Check that the device correctly handles a broken "
                        "(non-json) config message."
                    ),
                }
            }
        }
    },
    "schemas": {},
    "start_time": "2026-09-21T15:35:16Z",
    "status": {
        "category": "validation.feature.sequence",
        "level": 300,
        "message": "Run completed",
        "timestamp": "2026-09-21T15:40:16Z",
    },
    "timestamp": "2026-09-21T15:40:16Z",
    "udmi_version": "1.5.5-176-g1be0eb2ca-dirty",
}

#: The RESULT.log the same run wrote, byte for byte.
RECORDED_RESULT_LOG = (
    "CPBLTY skip system broken_config.status ALPHA 0/0 Never executed\n"
    "CPBLTY skip system broken_config.logging ALPHA 0/0 Never executed\n"
    "RESULT fail system broken_config STABLE 0/8 "
    "Timeout waiting for initial device state\n"
)


@pytest.fixture(scope="module")
def site_report():
    return compliance.site_compliance(UDMI_ROOT, SITE_MODEL)


def _make_site_model(root, device_ids):
    """Builds a minimal but genuine site model directory under `root`."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "cloud_iot_config.json").write_text(
        json.dumps({
            "site_name": "COMPLIANCE-FIXTURE",
            "registry_id": "CF-1",
            "iot_provider": "mqtt",
            "project_id": "//mqtt/localhost:18833",
        }),
        encoding="utf-8",
    )
    for device_id in device_ids:
        device_dir = root / "devices" / device_id
        device_dir.mkdir(parents=True)
        (device_dir / "metadata.json").write_text(
            json.dumps({"system": {"hardware": {"make": "ACME", "model": "X"}}}),
            encoding="utf-8",
        )
    (root / "out").mkdir()
    return root


@pytest.fixture
def recorded_site(tmp_path):
    """A site model holding `RECORDED_RUN` exactly as the sequencer wrote it."""
    root = _make_site_model(tmp_path / "recorded_site", ["AHU-1"])
    (root / "out" / "sequencer_AHU-1.json").write_text(
        json.dumps(RECORDED_RUN, indent=2), encoding="utf-8"
    )
    device_out = root / "out" / "devices" / "AHU-1"
    device_out.mkdir(parents=True)
    (device_out / "RESULT.log").write_text(RECORDED_RESULT_LOG, encoding="utf-8")
    (device_out / "results.md").write_text(
        "| Device | AHU-1 |\n| Result | fail |\n", encoding="utf-8"
    )
    return root


# ------------------------------------------------------------- site scope ---
def test_every_discovered_device_appears_in_the_matrix(site_report):
    """A device missing from the matrix would read as full coverage."""
    discovered = [d["device_id"] for d in discovery.list_devices(UDMI_ROOT, SITE_MODEL)]
    reported = [d["device_id"] for d in site_report["devices"]]

    assert discovered, "udmi_site_model must contain devices"
    assert sorted(reported) == sorted(discovered)
    assert site_report["site_model"] == SITE_MODEL


def test_broken_config_is_reported_exactly_as_recorded(recorded_site):
    report = compliance.site_compliance(str(recorded_site.parent), recorded_site.name)
    device = next(d for d in report["devices"] if d["device_id"] == "AHU-1")

    assert device["has_results"] is True
    assert device["reason"] is None
    assert device["last_run"]
    assert device["udmi_version"]
    assert device["status_message"] == "Run completed"

    sequence = next(s for s in device["sequences"] if s["name"] == "broken_config")
    assert sequence["feature"] == "system"
    assert sequence["result"] == "fail"
    assert sequence["stage"] == "stable"
    assert sequence["score"] == {"value": 0, "total": 8}
    assert sequence["message"] == "Timeout waiting for initial device state"
    assert sequence["summary"] == (
        "Check that the device correctly handles a broken (non-json) config message."
    )
    assert sequence["timestamp"]

    assert device["counts"]["fail"] >= 1
    assert device["score"]["total"] >= 8


def test_unexpected_verdicts_are_not_bucketed_as_pass_or_fail(site_report):
    """`errr` runs must stay visible instead of being folded into a bucket.

    The site model really does contain aborted runs recorded as `errr`. Counting
    them as failures would report a device that never got to run as a device
    that ran and failed every sequence, so each bucket is pinned to the exact
    number of sequences carrying that verdict.
    """
    verdicts = set()
    for device in site_report["devices"]:
        counts = device["counts"]
        results = [s["result"] for s in device["sequences"]]
        verdicts.update(results)

        assert counts["total"] == len(results)
        for bucket in ("pass", "fail", "skip"):
            assert counts[bucket] == results.count(bucket), (
                f"{device['device_id']}: '{bucket}' count must be exactly the "
                "sequences reporting that verdict, with no unknown verdicts added"
            )
        for result in results:
            assert result == result.lower()

    unexpected = verdicts - set(compliance.RESULT_BUCKETS)
    assert "errr" in unexpected, (
        "This test is only meaningful while the site model retains its real "
        "'errr' results; they are the verdicts at risk of being mis-bucketed"
    )


def test_aborted_runs_are_excluded_from_every_bucket(site_report):
    """AHU-22's run never reached the device; nothing may be scored pass/fail/skip."""
    device = next(d for d in site_report["devices"] if d["device_id"] == "AHU-22")

    assert device["has_results"] is True
    assert device["counts"]["total"] > 0
    assert {s["result"] for s in device["sequences"]} == {"errr"}
    assert device["counts"]["pass"] == 0
    assert device["counts"]["fail"] == 0
    assert device["counts"]["skip"] == 0
    assert device["sequences"][0]["message"] == "Reflector is not currently active"


def test_totals_aggregate_the_per_device_counts(site_report):
    totals = site_report["totals"]
    devices = site_report["devices"]

    assert totals["devices"] == len(devices)
    assert totals["devices_with_results"] == sum(
        1 for d in devices if d["has_results"]
    )
    for bucket in ("pass", "fail", "skip", "total"):
        assert totals[bucket] == sum(d["counts"][bucket] for d in devices)
    assert totals["total"] > 0, "The real site model has recorded sequences"


def test_reports_list_only_files_that_exist(site_report):
    site_dir = discovery.resolve_site_model(UDMI_ROOT, SITE_MODEL)

    for device in site_report["devices"]:
        assert set(device["reports"]) <= set(compliance.REPORT_KINDS)
        for kind in compliance.REPORT_KINDS:
            path = compliance._report_path(site_dir, device["device_id"], kind)
            assert os.path.isfile(path) == (kind in device["reports"]), (
                f"{device['device_id']}/{kind} presence must match disk"
            )

    ahu1 = next(d for d in site_report["devices"] if d["device_id"] == "AHU-1")
    assert set(ahu1["reports"]) == {"results_md", "result_log", "sequencer_json"}


# --------------------------------------------------------- honest absence ---
def test_device_without_sequencer_json_is_untested_not_zero_percent(tmp_path):
    site = _make_site_model(tmp_path / "fixture_site", ["NEW-1"])

    report = compliance.site_compliance(UDMI_ROOT, str(site))
    device = report["devices"][0]

    assert device["device_id"] == "NEW-1"
    assert device["has_results"] is False
    assert device["sequences"] == []
    assert device["counts"] == {"pass": 0, "fail": 0, "skip": 0, "total": 0}
    assert "sequencer_NEW-1.json" in device["reason"]
    assert str(site / "out") in device["reason"]
    assert device["reports"] == []

    assert report["totals"]["devices"] == 1
    assert report["totals"]["devices_with_results"] == 0


def test_malformed_sequencer_json_surfaces_the_parse_error(tmp_path):
    site = _make_site_model(tmp_path / "broken_site", ["BAD-1"])
    (site / "out" / "sequencer_BAD-1.json").write_text("{not json", encoding="utf-8")

    report = compliance.site_compliance(UDMI_ROOT, str(site))
    device = report["devices"][0]

    assert device["has_results"] is False
    assert "Invalid sequencer results" in device["reason"]
    assert "sequencer_BAD-1.json" in device["reason"]
    # The json module's own diagnostic, not a generic message.
    assert "Expecting" in device["reason"]
    assert device["counts"]["total"] == 0
    # Still downloadable for inspection even though it cannot be scored.
    assert device["reports"] == ["sequencer_json"]


def test_non_object_sequencer_json_is_rejected_not_scored(tmp_path):
    site = _make_site_model(tmp_path / "list_site", ["ODD-1"])
    (site / "out" / "sequencer_ODD-1.json").write_text("[]", encoding="utf-8")

    device = compliance.site_compliance(UDMI_ROOT, str(site))["devices"][0]

    assert device["has_results"] is False
    assert "expected a JSON object" in device["reason"]


def test_unknown_site_model_fails_fast():
    with pytest.raises(discovery.DiscoveryError, match="not found"):
        compliance.site_compliance(UDMI_ROOT, "sites/definitely_not_a_site_model")


# --------------------------------------------------------------- reports ----
@pytest.mark.parametrize(
    "kind,content_type,suffix",
    [
        ("results_md", "text/markdown", "results.md"),
        ("result_log", "text/plain", "RESULT.log"),
        ("sequencer_json", "application/json", "sequencer.json"),
    ],
)
def test_device_report_returns_real_bytes(kind, content_type, suffix):
    report = compliance.device_report(UDMI_ROOT, SITE_MODEL, "AHU-1", kind)

    assert report["content_type"] == content_type
    assert report["filename"] == f"AHU-1_{suffix}"
    assert "AHU-1" in report["filename"]
    assert isinstance(report["content"], bytes)
    assert report["size"] == len(report["content"]) > 0
    assert report["path"].startswith(SITE_MODEL)
    assert not os.path.isabs(report["path"]), "In-repo paths are repo-relative"


def test_report_content_is_the_file_verbatim(recorded_site):
    root, name = str(recorded_site.parent), recorded_site.name
    on_disk = open(
        os.path.join(str(recorded_site), "out", "devices", "AHU-1", "RESULT.log"), "rb"
    ).read()

    report = compliance.device_report(root, name, "AHU-1", "result_log")

    assert report["content"] == on_disk
    assert b"RESULT fail system broken_config STABLE 0/8" in report["content"]


def test_sequencer_json_report_parses_back_to_the_source_document(recorded_site):
    report = compliance.device_report(
        str(recorded_site.parent), recorded_site.name, "AHU-1", "sequencer_json"
    )
    document = json.loads(report["content"].decode("utf-8"))

    assert document == RECORDED_RUN
    assert document["features"]["system"]["sequences"]["broken_config"]["result"] == "fail"


def test_unknown_report_kind_lists_the_valid_kinds():
    with pytest.raises(ComplianceError) as excinfo:
        compliance.device_report(UDMI_ROOT, SITE_MODEL, "AHU-1", "pdf")

    message = str(excinfo.value)
    assert "pdf" in message
    for kind in ("results_md", "result_log", "sequencer_json"):
        assert kind in message


def test_missing_report_names_the_path_it_looked_for():
    """AHU-22 has no results.md; the error must say exactly what is absent."""
    with pytest.raises(ComplianceError) as excinfo:
        compliance.device_report(UDMI_ROOT, SITE_MODEL, "AHU-22", "results_md")

    message = str(excinfo.value)
    assert "out/devices/AHU-22/results.md" in message
    assert "does not exist" in message


@pytest.mark.parametrize(
    "device_id",
    ["../AHU-1", "..", "devices/AHU-1", "AHU-1/../../etc", "..\\AHU-1"],
)
def test_device_id_cannot_traverse_out_of_the_site_model(device_id):
    with pytest.raises(ComplianceError, match="Invalid device_id"):
        compliance.device_report(UDMI_ROOT, SITE_MODEL, device_id, "results_md")


def test_empty_device_id_is_rejected():
    with pytest.raises(ComplianceError, match="device_id parameter is required"):
        compliance.device_report(UDMI_ROOT, SITE_MODEL, "", "results_md")


def test_unknown_device_is_reported_by_name():
    with pytest.raises(ComplianceError, match="NOPE-9"):
        compliance.device_report(UDMI_ROOT, SITE_MODEL, "NOPE-9", "results_md")


def test_oversized_report_is_refused_rather_than_truncated(tmp_path, monkeypatch):
    site = _make_site_model(tmp_path / "big_site", ["BIG-1"])
    (site / "out" / "sequencer_BIG-1.json").write_text("{}" + " " * 64, encoding="utf-8")
    monkeypatch.setattr(compliance, "MAX_REPORT_BYTES", 8)

    with pytest.raises(ComplianceError, match="exceeding the 8 byte download limit"):
        compliance.device_report(UDMI_ROOT, str(site), "BIG-1", "sequencer_json")
