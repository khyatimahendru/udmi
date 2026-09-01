"""Unit tests for mantis.tools.schemas."""

import pytest
from mantis.tools.schemas import inspect_udmi_schema, list_udmi_schemas


def test_list_udmi_schemas():
    schemas = list_udmi_schemas()
    assert len(schemas) > 0
    names = [s["name"] for s in schemas]
    assert "pointset" in names or "events_pointset" in names
    assert "metadata" in names


def test_inspect_udmi_schema_valid():
    res = inspect_udmi_schema("pointset")
    assert res["status"] == "SUCCESS"
    assert "schema" in res
    assert "properties" in res["schema"]


def test_inspect_udmi_schema_sub_path():
    res = inspect_udmi_schema("pointset", sub_path="properties.points")
    assert res["status"] == "SUCCESS"
    assert "schema" in res


def test_inspect_udmi_schema_list_all():
    res = inspect_udmi_schema("list")
    assert res["status"] == "SUCCESS"
    assert res["count"] > 0
    assert "schemas" in res


def test_inspect_udmi_schema_nonexistent():
    res = inspect_udmi_schema("nonexistent_schema_xyz")
    assert res["status"] == "ERROR"
    assert "not found" in res["error"]
