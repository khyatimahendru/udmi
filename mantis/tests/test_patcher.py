"""Unit tests for mantis.tools.patcher."""

import json
import os
import pytest
from mantis.tools.patcher import patch_site_model, deep_merge


def test_deep_merge():
    target = {"a": 1, "b": {"c": 2, "d": 3}}
    updates = {"b": {"c": 99}, "e": 5}
    res = deep_merge(target, updates)
    assert res["a"] == 1
    assert res["b"]["c"] == 99
    assert res["b"]["d"] == 3
    assert res["e"] == 5


def test_patch_site_model_dry_run(tmp_path):
    # Setup temporary site model
    site_dir = tmp_path / "test_site"
    dev_dir = site_dir / "devices" / "DEV-1"
    dev_dir.mkdir(parents=True)
    meta_file = dev_dir / "metadata.json"
    meta_file.write_text(json.dumps({"pointset": {"sample_rate_sec": 60}}, indent=2) + "\n")

    res = patch_site_model(
        site_model=str(site_dir),
        device_id="DEV-1",
        patch_data={"pointset": {"sample_rate_sec": 10}},
        dry_run=True,
    )
    assert res["status"] == "DRY_RUN"
    assert res["applied"] is False
    assert "-    \"sample_rate_sec\": 60" in res["diff"]
    assert "+    \"sample_rate_sec\": 10" in res["diff"]

    # File should not have changed
    with open(meta_file, "r") as f:
        data = json.load(f)
    assert data["pointset"]["sample_rate_sec"] == 60


def test_patch_site_model_apply(tmp_path):
    site_dir = tmp_path / "test_site"
    dev_dir = site_dir / "devices" / "DEV-1"
    dev_dir.mkdir(parents=True)
    meta_file = dev_dir / "metadata.json"
    meta_file.write_text(json.dumps({"pointset": {"sample_rate_sec": 60}}, indent=2) + "\n")

    res = patch_site_model(
        site_model=str(site_dir),
        device_id="DEV-1",
        patch_data={"pointset": {"sample_rate_sec": 10}},
        dry_run=False,
    )
    assert res["status"] == "PATCHED"
    assert res["applied"] is True
    assert os.path.isfile(res["backup"])

    with open(meta_file, "r") as f:
        data = json.load(f)
    assert data["pointset"]["sample_rate_sec"] == 10
