"""Unit tests for mantis.skills."""

import pytest
from mantis.skills import SkillManager


def test_skills_discovery():
    mgr = SkillManager()
    skills = mgr.list_skills()
    assert len(skills) >= 3
    names = [s["name"] for s in skills]
    assert "log-analysis" in names
    assert "component-guide" in names
    assert "investigation-strategy" in names


def test_get_skill():
    mgr = SkillManager()
    skill = mgr.get_skill("log-analysis")
    assert skill is not None
    assert skill.name == "log-analysis"
    assert "Distributed Log Analysis" in skill.content
    assert skill.is_builtin is True


def test_match_skills():
    mgr = SkillManager()
    matched = mgr.match_skills("Why did the test fail with stale state in log analysis?")
    assert len(matched) > 0
    names = [s.name for s in matched]
    assert "log-analysis" in names


def test_get_system_prompt_catalog():
    mgr = SkillManager()
    catalog = mgr.get_system_prompt_catalog()
    assert "Available Domain Skills Catalog" in catalog
    assert "log-analysis" in catalog
