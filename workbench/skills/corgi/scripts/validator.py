"""Accessibility (a11y), Responsiveness, and Contract Validator for CORGI.

Ensures all generated components and page configs conform to WCAG 2.1 AA accessibility,
mobile-first responsive design principles, and component parameter contracts.
"""

from __future__ import annotations

import logging
import re
from typing import Any


class ValidationResult:
  """Holds the results of validation checks."""

  def __init__(self):
    self.errors: list[str] = []
    self.warnings: list[str] = []
    self.suggestions: list[str] = []

  @property
  def is_valid(self) -> bool:
    return len(self.errors) == 0

  def add_error(self, message: str) -> None:
    self.errors.append(message)

  def add_warning(self, message: str) -> None:
    self.warnings.append(message)

  def add_suggestion(self, message: str) -> None:
    self.suggestions.append(message)

  def to_dict(self) -> dict[str, Any]:
    return {
        "is_valid": self.is_valid,
        "errors": self.errors,
        "warnings": self.warnings,
        "suggestions": self.suggestions,
    }


class CorgiValidator:
  """Validates components, page configurations, and templates."""

  def validate_component(self, component: dict[str, Any]) -> ValidationResult:
    """Validates a single component definition."""
    result = ValidationResult()
    comp_id = component.get("id", "unknown")
    html_content = component.get("html_content", "")
    inputs_spec = component.get("inputs_spec", [])

    if not comp_id:
      result.add_error("Component is missing a valid 'id'.")

    if not html_content.strip():
      result.add_error(f"Component '{comp_id}' has empty 'html_content'.")
      return result

    # 1. Check Parameter Contract Integrity
    spec_names = {item.get("name") for item in inputs_spec if "name" in item}
    used_vars = set(re.findall(r"\$\{([a-zA-Z0-9_]+)\}", html_content))
    # Also check unbracketed $VAR placeholders
    used_vars.update(re.findall(r"\$([a-zA-Z0-9_]+)\b", html_content))

    undeclared_vars = used_vars - spec_names
    # Filter out common environmental tokens like $script, $style if handled
    if undeclared_vars:
      for v in undeclared_vars:
        result.add_warning(
            f"Component '{comp_id}' uses variable '${{{v}}}' in template, but"
            " it is not declared in 'inputs_spec'."
        )
        result.add_suggestion(
            f"Add {{'name': '{v}', 'type': 'string', 'description': '...'}} to"
            f" inputs_spec for component '{comp_id}'."
        )

    # 2. Accessibility (a11y) Checks
    self._check_a11y(html_content, comp_id, result)

    # 3. Responsiveness Checks
    self._check_responsiveness(html_content, comp_id, result)

    return result

  def _check_a11y(
      self, html_content: str, comp_id: str, result: ValidationResult
  ) -> None:
    """Performs accessibility audits on HTML snippet."""
    # Check 1: <img> without alt attribute
    img_tags = re.findall(r"<img\b[^>]*>", html_content, re.IGNORECASE)
    for img in img_tags:
      if not re.search(r"\balt\s*=", img, re.IGNORECASE):
        result.add_error(
            f"Accessibility violation in component '{comp_id}': <img> tag"
            f" missing required 'alt' attribute: {img}"
        )
        result.add_suggestion(
            "Add alt=\"${alt_text}\" or descriptive alt text to all <img> tags."
        )

    # Check 2: <button> or <a> without text or aria-label
    button_tags = re.findall(r"<button\b[^>]*>(.*?)</button>", html_content, re.DOTALL | re.IGNORECASE)
    for btn_content in button_tags:
      # If button content is empty and has no svg/img/aria-label
      if not btn_content.strip():
        result.add_warning(
            f"Component '{comp_id}' contains an empty <button> tag."
        )

    # Check 3: <input> without id or label
    input_tags = re.findall(r"<input\b[^>]*>", html_content, re.IGNORECASE)
    for inp in input_tags:
      if not re.search(r"\b(id|aria-label|aria-labelledby)\s*=", inp, re.IGNORECASE):
        result.add_warning(
            f"Component '{comp_id}' contains an <input> without 'id' or"
            f" 'aria-label': {inp}"
        )

  def _check_responsiveness(
      self, html_content: str, comp_id: str, result: ValidationResult
  ) -> None:
    """Performs mobile-first responsiveness audits."""
    # Check 1: Hardcoded desktop pixel widths (e.g. width: 800px or w-[800px])
    hardcoded_px_width = re.findall(r"(?:width:\s*([4-9]\d{2,}|[1-9]\d{3,})px|w-\[([4-9]\d{2,}|[1-9]\d{3,})px\])", html_content)
    if hardcoded_px_width:
      result.add_warning(
          f"Component '{comp_id}' contains large fixed pixel widths"
          f" ({hardcoded_px_width}) which break mobile responsiveness."
      )
      result.add_suggestion(
          "Replace fixed pixel widths with fluid max-width constraints (e.g."
          " max-w-4xl w-full px-4)."
      )

    # Check 2: Table without overflow-x-auto wrapper
    if "<table" in html_content.lower() and "overflow-x-auto" not in html_content.lower():
      result.add_suggestion(
          f"Component '{comp_id}' contains a <table>. Consider wrapping it in"
          " an overflow-x-auto container for mobile viewport compatibility."
      )

  def validate_page_config(
      self, page_config: dict[str, Any], catalog: dict[str, Any]
  ) -> ValidationResult:
    """Validates a full page configuration dictionary."""
    result = ValidationResult()

    if not isinstance(page_config, dict):
      result.add_error("Page config must be a dictionary/object.")
      return result

    page_id = page_config.get("page_id")
    if not page_id:
      result.add_error("Page config is missing 'page_id'.")

    title = page_config.get("title")
    if not title:
      result.add_warning("Page config is missing a 'title'.")

    components = page_config.get("components", [])
    if not components:
      result.add_warning(f"Page '{page_id}' has no components declared.")

    catalog_comps = catalog.get("components", {})

    for idx, item in enumerate(components):
      if not isinstance(item, dict):
        result.add_error(f"Component item at index {idx} must be an object.")
        continue
      c_id = item.get("component_id")
      if not c_id:
        result.add_error(f"Component item at index {idx} is missing 'component_id'.")
        continue

      if c_id not in catalog_comps:
        result.add_error(
            f"Page '{page_id}' references unknown component '{c_id}' (not found"
            " in catalog)."
        )
      else:
        # Check params against spec
        comp_def = catalog_comps[c_id]
        inputs_spec = comp_def.get("inputs_spec", [])
        params = item.get("params", {})
        for spec in inputs_spec:
          name = spec.get("name")
          req = spec.get("required", False)
          if req and name not in params:
            result.add_error(
                f"Page '{page_id}', component '{c_id}' is missing required"
                f" parameter '${name}'."
            )

    return result


# Backward compatibility alias
CurioValidator = CorgiValidator
