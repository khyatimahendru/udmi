"""Unit tests for mantis.tools.differential."""

import os
import pytest
from mantis.tools.differential import compare_test_runs


def test_compare_test_runs_basic(tmp_path):
    # Setup mock target run logs
    target_dir = tmp_path / "target_run"
    target_dir.mkdir()
    seq_log = target_dir / "sequence.log"
    seq_log.write_text("""
2026-08-26T12:45:00Z Starting test pointset_publish for AHU-1
2026-08-26T12:45:02Z Dispatched config RC:9a6ddf.00000134
2026-08-26T12:45:08Z Cutoff set: 2026-08-26T12:45:08Z
2026-08-26T12:45:09Z ignoring stale state update 2026-08-26T12:45:06Z
2026-08-26T12:47:08Z Stage timeout after 120s
2026-08-26T12:47:09Z RESULT: FAIL
""")

    res = compare_test_runs(target_run=str(target_dir))
    assert res["status"] == "SUCCESS"
    assert res["target_result"] == "FAIL"
    assert res["divergence_point"] == "STALE_STATE_IGNORED"
    assert "DIVERGENCE POINT" in res["differential_table"]
    assert "Cascading Failure" in res["differential_table"]
