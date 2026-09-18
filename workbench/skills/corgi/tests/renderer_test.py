"""Tests for CORGI deterministic renderer."""

import json
import os
import tempfile

try:
  from absl.testing import absltest as unittest_runner
except ImportError:
  import unittest as unittest_runner

try:
  from ..scripts import renderer
except (ImportError, ValueError):
  import sys
  sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
  import renderer


class RendererTest(unittest_runner.TestCase):

  def setUp(self):
    super().setUp()
    self.test_dir = tempfile.mkdtemp()
    self.corgi_dir = os.path.join(self.test_dir, ".corgi")
    os.makedirs(os.path.join(self.corgi_dir, "components"), exist_ok=True)

    # Setup a sample catalog
    self.catalog_data = {
        "version": "1.0.0",
        "components": {
            "btn_test": {
                "id": "btn_test",
                "name": "Test Button",
                "category": "atom",
                "html_content": '<a href="${url}" class="btn">${label}</a>',
                "inputs_spec": [
                    {"name": "label", "type": "string", "default": "Click"},
                    {"name": "url", "type": "string", "default": "#"},
                ],
            },
            "card_test": {
                "id": "card_test",
                "name": "Test Card",
                "category": "molecule",
                "html_content": (
                    '<div class="card"><h3>${title}</h3><p>${body}</p><div>${button}</div></div>'
                ),
                "inputs_spec": [
                    {"name": "title", "type": "string", "default": "Title"},
                    {"name": "body", "type": "string", "default": "Body"},
                    {"name": "button", "type": "component"},
                ],
            },
            "grid_test": {
                "id": "grid_test",
                "name": "Test Grid",
                "category": "structure",
                "html_content": '<div class="grid">${items}</div>',
                "inputs_spec": [
                    {"name": "items", "type": "component_list"},
                ],
            },
        },
    }

    with open(
        os.path.join(self.corgi_dir, "catalog.json"), "w", encoding="utf-8"
    ) as f:
      json.dump(self.catalog_data, f)

    self.renderer = renderer.CorgiRenderer(self.corgi_dir)

  def test_render_single_atom(self):
    html = self.renderer.render_component(
        "btn_test", {"label": "Submit", "url": "/save"}
    )
    self.assertEqual(html, '<a href="/save" class="btn">Submit</a>')

  def test_render_default_values(self):
    html = self.renderer.render_component("btn_test", {})
    self.assertEqual(html, '<a href="#" class="btn">Click</a>')

  def test_render_nested_component(self):
    params = {
        "title": "Welcome",
        "body": "This is a test.",
        "button": {
            "component_id": "btn_test",
            "params": {"label": "Learn More", "url": "/docs"},
        },
    }
    html = self.renderer.render_component("card_test", params)
    expected = (
        '<div class="card"><h3>Welcome</h3><p>This is a'
        ' test.</p><div><a href="/docs" class="btn">Learn'
        " More</a></div></div>"
    )
    self.assertEqual(html, expected)

  def test_render_component_list(self):
    params = {
        "items": [
            {"component_id": "btn_test", "params": {"label": "Btn 1"}},
            {"component_id": "btn_test", "params": {"label": "Btn 2"}},
        ]
    }
    html = self.renderer.render_component("grid_test", params)
    self.assertIn('<a href="#" class="btn">Btn 1</a>', html)
    self.assertIn('<a href="#" class="btn">Btn 2</a>', html)

  def test_render_full_page(self):
    page_config = {
        "page_id": "home",
        "title": "My Test App",
        "components": [
            {
                "component_id": "card_test",
                "params": {"title": "Hello World", "body": "Page content."},
            }
        ],
    }
    page_html = self.renderer.render_page(page_config)
    self.assertIn("<title>My Test App</title>", page_html)
    self.assertIn("<h3>Hello World</h3>", page_html)
    self.assertIn("<p>Page content.</p>", page_html)


if __name__ == "__main__":
  unittest_runner.main()
