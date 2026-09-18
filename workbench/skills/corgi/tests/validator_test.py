"""Tests for CORGI accessibility and responsiveness validator."""

try:
  from absl.testing import absltest as unittest_runner
except ImportError:
  import unittest as unittest_runner

try:
  from ..scripts import validator
except (ImportError, ValueError):
  import os
  import sys
  sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
  import validator


class ValidatorTest(unittest_runner.TestCase):

  def setUp(self):
    super().setUp()
    self.validator = validator.CorgiValidator()

  def test_a11y_detects_missing_img_alt(self):
    comp = {
        "id": "bad_image_card",
        "html_content": '<div><img src="avatar.png"><h3>${title}</h3></div>',
        "inputs_spec": [{"name": "title", "type": "string"}],
    }
    result = self.validator.validate_component(comp)
    self.assertFalse(result.is_valid)
    self.assertTrue(
        any("missing required 'alt' attribute" in err for err in result.errors)
    )

  def test_a11y_passes_with_alt(self):
    comp = {
        "id": "good_image_card",
        "html_content": (
            '<div><img src="avatar.png" alt="${alt_text}"><h3>${title}</h3></div>'
        ),
        "inputs_spec": [
            {"name": "title", "type": "string"},
            {"name": "alt_text", "type": "string"},
        ],
    }
    result = self.validator.validate_component(comp)
    self.assertTrue(result.is_valid)

  def test_responsiveness_detects_hardcoded_desktop_width(self):
    comp = {
        "id": "unresponsive_card",
        "html_content": '<div style="width: 1024px;">Content</div>',
        "inputs_spec": [],
    }
    result = self.validator.validate_component(comp)
    self.assertTrue(result.is_valid)  # Large width triggers warning in validator
    self.assertTrue(
        any("break mobile responsiveness" in w for w in result.warnings)
    )

  def test_undeclared_param_warning(self):
    comp = {
        "id": "warn_comp",
        "html_content": '<div>${undeclared_var}</div>',
        "inputs_spec": [],
    }
    result = self.validator.validate_component(comp)
    self.assertTrue(result.is_valid)  # Warnings do not fail validity
    self.assertTrue(any("undeclared_var" in w for w in result.warnings))


if __name__ == "__main__":
  unittest_runner.main()
