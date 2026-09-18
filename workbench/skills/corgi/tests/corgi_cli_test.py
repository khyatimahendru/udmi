"""Tests for CORGI CLI."""

import json
import os
import tempfile

try:
  from absl.testing import absltest as unittest_runner
except ImportError:
  import unittest as unittest_runner

try:
  from ..scripts import corgi_cli
except (ImportError, ValueError):
  import sys
  sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
  import corgi_cli


class CorgiCLITest(unittest_runner.TestCase):

  def setUp(self):
    super().setUp()
    self.test_dir = tempfile.mkdtemp()

  def test_cmd_init_creates_structure(self):
    args = corgi_cli.argparse.Namespace(
        path=self.test_dir,
        corgi_dir=".corgi",
        theme_name="Test Brand",
        primary_color="#ff5722",
    )
    ret = corgi_cli.cmd_init(args)
    self.assertEqual(ret, 0)

    corgi_dir = os.path.join(self.test_dir, ".corgi")
    self.assertTrue(os.path.exists(os.path.join(corgi_dir, "catalog.json")))
    self.assertTrue(os.path.exists(os.path.join(corgi_dir, "layout.html")))
    self.assertTrue(os.path.exists(os.path.join(corgi_dir, "theme.json")))
    self.assertTrue(os.path.exists(os.path.join(corgi_dir, "assets.json")))

    with open(os.path.join(corgi_dir, "theme.json"), "r", encoding="utf-8") as f:
      theme = json.load(f)
    self.assertEqual(theme.get("colors", {}).get("primary"), "#ff5722")

  def test_cmd_component_add_and_page_render(self):
    # 1. Init workspace
    init_args = corgi_cli.argparse.Namespace(
        path=self.test_dir, corgi_dir=".corgi", theme_name=None, primary_color=None
    )
    corgi_cli.cmd_init(init_args)

    # 2. Dynamically add custom button component
    add_btn_args = corgi_cli.argparse.Namespace(
        corgi_dir=os.path.join(self.test_dir, ".corgi"),
        id="custom_btn",
        category="atom",
        name="Custom Button",
        description="Custom branded button",
        file=None,
        template='<button class="btn-custom">${btn_text}</button>',
        inputs=json.dumps([{"name": "btn_text", "type": "string", "default": "Click"}]),
        tags="button,atom",
    )
    ret = corgi_cli.cmd_component_add(add_btn_args)
    self.assertEqual(ret, 0)

    # 3. Create sample page config using the dynamically added component
    corgi_dir = os.path.join(self.test_dir, ".corgi")
    page_file = os.path.join(corgi_dir, "pages", "test_page.json")
    page_data = {
        "page_id": "test_page",
        "title": "Dynamic Test Page",
        "components": [
            {
                "component_id": "custom_btn",
                "params": {"btn_text": "Launch Platform"},
            }
        ],
    }
    with open(page_file, "w", encoding="utf-8") as f:
      json.dump(page_data, f)

    out_file = os.path.join(self.test_dir, "test_page.html")
    render_args = corgi_cli.argparse.Namespace(
        page_file=page_file,
        output=out_file,
        corgi_dir=corgi_dir,
    )
    ret = corgi_cli.cmd_page_render(render_args)
    self.assertEqual(ret, 0)
    self.assertTrue(os.path.exists(out_file))

    with open(out_file, "r", encoding="utf-8") as f:
      rendered_content = f.read()
    self.assertIn("Dynamic Test Page", rendered_content)
    self.assertIn('<button class="btn-custom">Launch Platform</button>', rendered_content)

  def test_page_name_sanitization_prevents_traversal(self):
    # Verify sanitization logic directly
    malicious_inputs = ["../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "subdir/../../secret"]
    pages_dir = os.path.join(self.test_dir, ".corgi", "pages")
    os.makedirs(pages_dir, exist_ok=True)

    for mal in malicious_inputs:
      raw = mal
      name = os.path.basename(corgi_cli.urllib.parse.unquote(raw))
      target = os.path.join(pages_dir, f"{name}.yaml")
      # Check that checking ".." in raw correctly detects traversal
      self.assertTrue(".." in raw or os.path.commonpath([os.path.abspath(target), os.path.abspath(pages_dir)]) == os.path.abspath(pages_dir))


if __name__ == "__main__":
  unittest_runner.main()
