"""Deterministic template and page renderer for CORGI UI Catalog.

Compiles declarative YAML/JSON page specifications and parameterized components
from the .corgi directory into coherent, responsive, and accessible HTML pages.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
from typing import Any


class RenderError(Exception):
  """Raised when an error occurs during component or page rendering."""


class CorgiRenderer:
  """Deterministic renderer that combines catalog components and layouts."""

  def __init__(self, corgi_dir: str = ".corgi"):
    """Initializes the CorgiRenderer.

    Args:
      corgi_dir: Path to the .corgi directory containing catalog.json,
        layout.html, components/, etc.
    """
    self.corgi_dir = os.path.abspath(corgi_dir)
    self.catalog_path = os.path.join(self.corgi_dir, "catalog.json")
    self.layout_path = os.path.join(self.corgi_dir, "layout.html")
    self.catalog: dict[str, Any] = self._load_catalog()

  def _load_catalog(self) -> dict[str, Any]:
    """Loads the component catalog from catalog.json."""
    if not os.path.exists(self.catalog_path):
      return {"components": {}, "version": "1.0.0"}
    try:
      with open(self.catalog_path, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception as e:
      logging.exception("Failed to load catalog from %s", self.catalog_path)
      raise RenderError(f"Failed to load catalog.json: {e}") from e

  def get_component(self, component_id: str) -> dict[str, Any] | None:
    """Retrieves component definition by ID from the catalog."""
    components = self.catalog.get("components", {})
    if component_id in components:
      comp = dict(components[component_id])
      # Resolve source content from relative file if specified
      if "file" in comp and comp["file"]:
        comp_file = os.path.join(self.corgi_dir, comp["file"])
        if os.path.exists(comp_file):
          with open(comp_file, "r", encoding="utf-8") as f:
            comp["html_content"] = f.read()
      return comp
    return None

  def get_layout(self, layout_name: str = "default") -> str:
    """Loads global layout HTML."""
    if os.path.exists(self.layout_path):
      with open(self.layout_path, "r", encoding="utf-8") as f:
        return f.read()
    # Fallback minimal HTML layout if layout.html does not exist
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        "  <meta charset=\"UTF-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "  <title>${PAGE_TITLE}</title>\n"
        "  <script src=\"https://cdn.tailwindcss.com\"></script>\n"
        "</head>\n<body class=\"bg-gray-50 text-gray-900\">\n"
        "  ${NAVBAR}\n"
        "  <main class=\"max-w-7xl mx-auto px-4 py-8\">\n"
        "    ${PAGE_CONTENT}\n"
        "  </main>\n"
        "  ${FOOTER}\n"
        "</body>\n</html>"
    )

  def render_component(
      self,
      component_id: str,
      params: dict[str, Any] | None = None,
  ) -> str:
    """Renders a single parameterized component by ID and input parameters.

    Args:
      component_id: The unique identifier of the component in the catalog.
      params: Dictionary of parameter values to inject.

    Returns:
      Rendered HTML string.

    Raises:
      RenderError: If component is not found in catalog.
    """
    params = params or {}
    comp = self.get_component(component_id)
    if not comp:
      raise RenderError(f"Component '{component_id}' not found in catalog.")

    html_template = comp.get("html_content", "")
    inputs_spec = comp.get("inputs_spec", [])

    return self._render_template(html_template, inputs_spec, params)

  def _render_template(
      self,
      template: str,
      inputs_spec: list[dict[str, Any]],
      params: dict[str, Any],
  ) -> str:
    """Internal helper to substitute parameters into a component template."""
    rendered = template

    # Index specifications by name for type checking and defaults
    spec_map = {item.get("name"): item for item in inputs_spec if "name" in item}

    # Handle all declared inputs
    for name, spec in spec_map.items():
      val = params.get(name, spec.get("default", ""))
      val_type = spec.get("type", "string")

      if val_type in ("component", "nested_component"):
        if isinstance(val, dict) and "component_id" in val:
          child_id = val.get("component_id", "")
          child_params = val.get("params", {})
          child_html = self.render_component(child_id, child_params)
        elif isinstance(val, str) and val:
          child_html = val
        else:
          child_html = ""
        rendered = self._substitute_var(rendered, name, child_html)

      elif val_type in ("component_list", "list[component]"):
        items_html = []
        if isinstance(val, list):
          for item in val:
            if isinstance(item, dict) and "component_id" in item:
              child_id = item.get("component_id", "")
              child_params = item.get("params", {})
              items_html.append(self.render_component(child_id, child_params))
            elif isinstance(item, str):
              items_html.append(item)
        rendered = self._substitute_var(rendered, name, "\n".join(items_html))

      elif val_type == "list[string]":
        if isinstance(val, list):
          # Join list items with newline
          rendered = self._substitute_var(rendered, name, "\n".join(str(x) for x in val))
        else:
          rendered = self._substitute_var(rendered, name, str(val))

      elif val_type == "boolean":
        bool_val = bool(val) if val is not None else False
        rendered = self._substitute_var(rendered, name, "true" if bool_val else "false")

      else:
        # String, number, etc.
        rendered = self._substitute_var(rendered, name, str(val) if val is not None else "")

    # Also substitute any direct parameters passed that weren't strictly in spec
    for k, v in params.items():
      if k not in spec_map:
        if isinstance(v, (str, int, float, bool)):
          rendered = self._substitute_var(rendered, k, str(v))

    return rendered

  def _substitute_var(self, template: str, var_name: str, value: str) -> str:
    """Substitutes ${VAR} and $VAR with the provided string value."""
    # Pattern for ${VAR_NAME}
    pattern_bracketed = re.compile(r"\$\{" + re.escape(var_name) + r"\}")
    template = pattern_bracketed.sub(lambda _: value, template)

    # Pattern for $VAR_NAME (boundary matched to avoid prefix clashes)
    pattern_simple = re.compile(r"\$" + re.escape(var_name) + r"(?![a-zA-Z0-9_])")
    template = pattern_simple.sub(lambda _: value, template)

    return template

  def render_page(self, page_config: dict[str, Any]) -> str:
    """Renders a full HTML page from a declarative page specification.

    Args:
      page_config: Dictionary containing page metadata and component tree.
        Expected keys:
          - page_id: str
          - title: str
          - slug: str (optional)
          - layout_id: str (optional)
          - navbar: dict | list (optional)
          - footer: dict | list (optional)
          - components: list[dict] (each containing 'component_id' and 'params')

    Returns:
      Full rendered HTML string.
    """
    page_title = page_config.get("title", "CORGI Application")
    layout_name = page_config.get("layout_id", "default")
    layout_html = self.get_layout(layout_name)

    # Render body components
    rendered_components = []
    comp_list = page_config.get("components", [])

    for entry in comp_list:
      if not isinstance(entry, dict):
        continue
      comp_id = entry.get("component_id")
      if not comp_id:
        continue
      params = entry.get("params", {})
      try:
        c_html = self.render_component(comp_id, params)
        rendered_components.append(c_html)
      except RenderError as e:
        logging.exception("Error rendering component %s on page", comp_id)
        error_box = (
            f'<div class="p-4 my-2 border border-red-300 bg-red-50 text-red-700'
            f' rounded-xl text-sm font-mono"><strong>[CORGI Render Error]</strong>'
            f' Component <code>{html.escape(comp_id)}</code> failed to render: '
            f'{html.escape(str(e))}</div>'
        )
        rendered_components.append(error_box)

    page_content = "\n\n".join(rendered_components)

    # Render Navbar
    navbar_config = page_config.get("navbar")
    if navbar_config and isinstance(navbar_config, dict) and "component_id" in navbar_config:
      navbar_html = self.render_component(
          navbar_config["component_id"], navbar_config.get("params", {})
      )
    else:
      navbar_html = ""

    # Render Footer
    footer_config = page_config.get("footer")
    if footer_config and isinstance(footer_config, dict) and "component_id" in footer_config:
      footer_html = self.render_component(
          footer_config["component_id"], footer_config.get("params", {})
      )
    else:
      footer_html = ""

    # Inject into global layout
    html_out = layout_html
    html_out = self._substitute_var(html_out, "PAGE_TITLE", page_title)
    html_out = self._substitute_var(html_out, "NAVBAR", navbar_html)
    html_out = self._substitute_var(html_out, "PAGE_CONTENT", page_content)
    html_out = self._substitute_var(html_out, "FOOTER", footer_html)

    return html_out


# Backward compatibility alias
CurioRenderer = CorgiRenderer
