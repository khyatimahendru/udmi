"""Unit tests for mantis.tools.diagnostics and empirical stability metrics."""

import os
import pytest
from mantis.models import ClaimStatus
from mantis.tools.diagnostics import diagnose_test_failure, evaluate_test_stability


def test_diagnose_schema_violation_failure(tmp_path):
    run_dir = tmp_path / "run_schema_err"
    run_dir.mkdir()
    seq_log = run_dir / "sequence.log"
    seq_log.write_text("""
2026-08-26T12:45:00Z Starting test pointset_publish for AHU-1
2026-08-26T12:45:02Z Schema validation error: missing required point 'filter_alarm'
2026-08-26T12:45:03Z RESULT: FAIL
""")

    res = diagnose_test_failure(
        test_id="pointset_publish",
        device_id="AHU-1",
        run_dir=str(run_dir),
    )

    assert res["status"] == "SUCCESS"
    assert res["competing_hypotheses"]["Schema Point Violation / Telemetry Malformation"]["status"] == ClaimStatus.CONFIRMED.value
    assert "missing required point" in res["root_cause"]


def test_diagnose_transport_failure(tmp_path):
    run_dir = tmp_path / "run_transport"
    run_dir.mkdir()
    seq_log = run_dir / "sequence.log"
    seq_log.write_text("""
2026-08-26T12:45:00Z Starting test pointset_publish for AHU-1
2026-08-26T12:45:02Z ConnectionRefusedError: Connection refused by broker on port 46432
2026-08-26T12:45:03Z RESULT: FAIL
""")

    res = diagnose_test_failure(
        test_id="pointset_publish",
        device_id="AHU-1",
        run_dir=str(run_dir),
    )

    assert res["status"] == "SUCCESS"
    assert res["competing_hypotheses"]["Transport / TLS Connection Failure"]["status"] == ClaimStatus.CONFIRMED.value
    assert "Network transport" in res["root_cause"]


def test_diagnose_auth_failure(tmp_path):
    run_dir = tmp_path / "run_auth"
    run_dir.mkdir()
    seq_log = run_dir / "sequence.log"
    seq_log.write_text("""
2026-08-26T12:45:00Z Starting test pointset_publish for AHU-1
2026-08-26T12:45:02Z Connection Refused: not authorised (Bad username or password)
2026-08-26T12:45:03Z RESULT: FAIL
""")

    res = diagnose_test_failure(
        test_id="pointset_publish",
        device_id="AHU-1",
        run_dir=str(run_dir),
    )

    assert res["status"] == "SUCCESS"
    assert res["competing_hypotheses"]["Authentication / Authorization Rejection"]["status"] == ClaimStatus.CONFIRMED.value
    assert "Authentication rejected" in res["root_cause"]


def test_diagnose_generic_stage_timeout(tmp_path):
    run_dir = tmp_path / "run_timeout"
    run_dir.mkdir()
    seq_log = run_dir / "sequence.log"
    seq_log.write_text("""
2026-08-26T12:45:00Z Starting test pointset_publish for AHU-1
2026-08-26T12:47:00Z Stage timeout after 120s waiting for telemetry echo
2026-08-26T12:47:01Z RESULT: FAIL
""")

    res = diagnose_test_failure(
        test_id="pointset_publish",
        device_id="AHU-1",
        run_dir=str(run_dir),
    )

    assert res["status"] == "SUCCESS"
    assert res["competing_hypotheses"]["Stage Timeout Execution Failure"]["status"] == ClaimStatus.CONFIRMED.value


def test_evaluate_test_stability(tmp_path):
    # Create 3 test runs: 2 PASS, 1 FAIL
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    run1 = runs_dir / "run_pass_1"
    run1.mkdir()
    (run1 / "sequence.log").write_text("RESULT: PASS\n")

    run2 = runs_dir / "run_pass_2"
    run2.mkdir()
    (run2 / "sequence.log").write_text("RESULT: PASS\n")

    run3 = runs_dir / "run_fail_1"
    run3.mkdir()
    (run3 / "sequence.log").write_text("""
UnrecognizedPropertyException: Unrecognized field "bad_prop"
RESULT: FAIL
""")

    stab = evaluate_test_stability(base_dir=str(runs_dir))
    assert stab["status"] == "SUCCESS"
    assert stab["total_runs"] == 3
    assert stab["pass_count"] == 2
    assert stab["fail_count"] == 1
    assert pytest.approx(stab["pass_rate_pct"], 0.1) == 66.7
    assert stab["failure_breakdown"].get("Jackson Deserialization Failure") == 1
    assert "System Stability Score" in stab["summary_report"]


def test_diagnose_multiline_jackson_with_caused_by(tmp_path):
    run_dir = tmp_path / "run_multiline_jackson"
    run_dir.mkdir()
    seq_log = run_dir / "sequence.log"
    seq_log.write_text("""
2026-08-26T12:45:00Z Starting test pointset_publish for AHU-1
java.lang.RuntimeException: Failed to load device config
\tat com.google.daq.mqtt.sequencer.SequenceBase.setup(SequenceBase.java:145)
Caused by: com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException: Unrecognized field "extra_key" (class udmi.schema.Metadata)
 at [Source: (String)"{\\n  \\"extra_key\\": 123\\n}"; line: 2, column: 15]
\tat com.fasterxml.jackson.databind.exc.PropertyBindingException.from(PropertyBindingException.java:62)
2026-08-26T12:45:03Z RESULT: FAIL
""")

    res = diagnose_test_failure(
        test_id="pointset_publish",
        device_id="AHU-1",
        run_dir=str(run_dir),
    )

    assert res["status"] == "SUCCESS"
    assert res["competing_hypotheses"]["Jackson Deserialization Failure"]["status"] == ClaimStatus.CONFIRMED.value
    assert "extra_key" in res["root_cause"] or "Unrecognized field" in res["root_cause"]


def test_diagnose_multiline_assertion_timeout(tmp_path):
    run_dir = tmp_path / "run_multiline_timeout"
    run_dir.mkdir()
    seq_log = run_dir / "sequence.log"
    seq_log.write_text("""
2026-08-26T12:45:00Z Starting test pointset_publish for AHU-1
java.lang.AssertionError: Sequence failed: Timeout waiting for state sync (stage 2) after 120s
\tat org.junit.Assert.fail(Assert.java:89)
\tat com.google.daq.mqtt.sequencer.SequenceRunner.waitForState(SequenceRunner.java:312)
2026-08-26T12:47:03Z RESULT: FAIL
""")

    res = diagnose_test_failure(
        test_id="pointset_publish",
        device_id="AHU-1",
        run_dir=str(run_dir),
    )

    assert res["status"] == "SUCCESS"
    assert res["competing_hypotheses"]["Stage Timeout Execution Failure"]["status"] == ClaimStatus.CONFIRMED.value
