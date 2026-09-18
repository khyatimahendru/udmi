"""CORGI Command Line Interface (CLI).

The main CLI tool for CORGI (Catalog-driven Orchestration of Responsive Graphical Interfaces).
Provides commands for:
- Initializing .corgi workspace and directory structure (init)
- Searching, adding, and inspecting parameterized components (component list, get, search, add)
- Deterministic page rendering from declarative YAML configs (page render)
- Validating components and pages for a11y, responsiveness, and contracts (page validate)
- Launching local interactive preview server and option picker (preview)
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import sys
from typing import Any
import urllib.parse

try:
  from . import renderer
  from . import validator
except (ImportError, ValueError):
  try:
    import renderer
    import validator
  except ImportError:
    from google3.corp.floe.agents.curio.scripts import renderer
    from google3.corp.floe.agents.curio.scripts import validator

# Try importing yaml for declarative page configs; fall back to JSON if unavailable.
try:
  import yaml
except ImportError:
  yaml = None


def _load_yaml_or_json(file_path: str) -> dict[str, Any]:
  """Loads YAML or JSON configuration file."""
  with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()
  if yaml is not None:
    try:
      data = yaml.safe_load(content)
      if isinstance(data, dict):
        return data
    except Exception:
      pass
  return json.loads(content)


def cmd_init(args: argparse.Namespace) -> int:
  """Initializes a new .corgi directory structure with theme and layout skeletons."""
  project_root = os.path.abspath(args.path)
  corgi_dir = os.path.join(project_root, args.corgi_dir or ".corgi")

  print(f"Initializing CORGI workspace in: {corgi_dir}")
  os.makedirs(os.path.join(corgi_dir, "components", "structure"), exist_ok=True)
  os.makedirs(os.path.join(corgi_dir, "components", "atoms"), exist_ok=True)
  os.makedirs(os.path.join(corgi_dir, "components", "molecules"), exist_ok=True)
  os.makedirs(os.path.join(corgi_dir, "pages"), exist_ok=True)

  # 1. Base Layout HTML skeleton
  layout_file = os.path.join(corgi_dir, "layout.html")
  if not os.path.exists(layout_file):
    with open(layout_file, "w", encoding="utf-8") as f:
      f.write("""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${PAGE_TITLE}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" />
  <style>
    body { font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  </style>
</head>
<body class="bg-gray-50 dark:bg-zinc-950 text-gray-900 dark:text-zinc-100 min-h-screen flex flex-col antialiased">
  <header class="sticky top-0 z-50 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border-b border-gray-200 dark:border-zinc-800 transition-colors">
    ${NAVBAR}
  </header>

  <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-12">
    ${PAGE_CONTENT}
  </main>

  <footer class="bg-white dark:bg-zinc-900 border-t border-gray-200 dark:border-zinc-800 py-8 transition-colors">
    ${FOOTER}
  </footer>
</body>
</html>
""")
    print(f"  Created {os.path.basename(corgi_dir)}/layout.html")

  # 2. Theme & Design Tokens JSON skeleton
  theme_file = os.path.join(corgi_dir, "theme.json")
  if not os.path.exists(theme_file):
    theme_data = {
        "theme_name": args.theme_name or "Custom Surface Theme",
        "version": "1.0.0",
        "colors": {
            "primary": args.primary_color or "#1a73e8",
            "primary_hover": "#1557b0",
            "background": "#fafafa",
            "surface": "#ffffff",
            "text": "#202124",
            "muted": "#5f6368",
            "border": "#dadce0"
        },
        "typography": {
            "main": "Google Sans, sans-serif",
            "code": "Roboto Mono, monospace"
        },
        "radii": {
            "card": "16px",
            "pill": "9999px",
            "button": "8px"
        }
    }
    with open(theme_file, "w", encoding="utf-8") as f:
      json.dump(theme_data, f, indent=2)
    print(f"  Created {os.path.basename(corgi_dir)}/theme.json")

  # 3. Assets index
  assets_file = os.path.join(corgi_dir, "assets.json")
  if not os.path.exists(assets_file):
    assets_data = {
        "images": {},
        "icons": {},
        "external_fonts": [
            "https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&display=swap"
        ]
    }
    with open(assets_file, "w", encoding="utf-8") as f:
      json.dump(assets_data, f, indent=2)
    print(f"  Created {os.path.basename(corgi_dir)}/assets.json")

  # 4. Catalog JSON (Clean, ready for agent-scanned or agent-generated components)
  catalog_file = os.path.join(corgi_dir, "catalog.json")
  if not os.path.exists(catalog_file):
    catalog_data = {
        "version": "1.0.0",
        "description": "CORGI UI Component Catalog",
        "components": {}
    }
    with open(catalog_file, "w", encoding="utf-8") as f:
      json.dump(catalog_data, f, indent=2)
    print(f"  Created {os.path.basename(corgi_dir)}/catalog.json")

  print("\nCORGI workspace initialization complete!")
  print("The agent can now scan existing UI code or generate customized starter primitives into .corgi/.")
  return 0


def cmd_component_add(args: argparse.Namespace) -> int:
  """Registers a new component in .corgi/catalog.json."""
  corgi_dir = os.path.abspath(args.corgi_dir or ".corgi")
  catalog_path = os.path.join(corgi_dir, "catalog.json")

  if not os.path.exists(catalog_path):
    print(f"Error: Catalog file '{catalog_path}' not found. Run 'corgi init' first.", file=sys.stderr)
    return 1

  with open(catalog_path, "r", encoding="utf-8") as f:
    catalog_data = json.load(f)

  comp_id = args.id
  category = args.category.lower()
  name = args.name or comp_id.replace("_", " ").title()
  description = args.description or f"{category.capitalize()} component"

  # Inputs spec parsing
  inputs_spec = []
  if args.inputs:
    try:
      inputs_spec = json.loads(args.inputs)
    except Exception:
      print("Warning: Could not parse --inputs JSON; defaulting to empty spec.")

  # Normalize folder: structure, atoms, molecules
  cat_dir = "atoms" if category in ("atom", "atoms") else ("molecules" if category in ("molecule", "molecules") else "structure")
  rel_file_path = f"components/{cat_dir}/{comp_id}.html"
  dest_file = os.path.join(corgi_dir, rel_file_path)
  os.makedirs(os.path.dirname(dest_file), exist_ok=True)

  if args.file and os.path.exists(args.file):
    with open(args.file, "r", encoding="utf-8") as src_f:
      content = src_f.read()
    with open(dest_file, "w", encoding="utf-8") as dest_f:
      dest_f.write(content)
  elif args.template:
    with open(dest_file, "w", encoding="utf-8") as dest_f:
      dest_f.write(args.template)

  tags = [t.strip() for t in args.tags.split(",")] if args.tags else [category]

  catalog_data.setdefault("components", {})[comp_id] = {
      "id": comp_id,
      "name": name,
      "category": category,
      "description": description,
      "file": rel_file_path,
      "inputs_spec": inputs_spec,
      "tags": tags
  }

  with open(catalog_path, "w", encoding="utf-8") as f:
    json.dump(catalog_data, f, indent=2)

  print(f"✅ Registered component '{comp_id}' in catalog ({rel_file_path}).")
  return 0


def cmd_component_list(args: argparse.Namespace) -> int:
  """Lists all components registered in the catalog."""
  corgi_dir = os.path.abspath(args.corgi_dir or ".corgi")
  renderer_inst = renderer.CorgiRenderer(corgi_dir)
  components = renderer_inst.catalog.get("components", {})

  category_filter = args.category.lower() if args.category else "all"

  print(f"=== CORGI Component Catalog ({len(components)} components) ===\n")
  if not components:
    print("  (Catalog is currently empty. The agent will scan or generate components into .corgi/components/.)\n")
    return 0

  for comp_id, comp in components.items():
    cat = comp.get("category", "atom")
    if category_filter not in ("all", cat):
      continue

    print(f"• ID: {comp_id}")
    print(f"  Name: {comp.get('name', comp_id)}")
    print(f"  Category: {cat.upper()}")
    print(f"  Description: {comp.get('description', '')}")
    inputs = comp.get("inputs_spec", [])
    if inputs:
      input_names = [f"${inp['name']} ({inp.get('type', 'str')})" for inp in inputs if 'name' in inp]
      print(f"  Parameters: {', '.join(input_names)}")
    tags = comp.get("tags", [])
    if tags:
      print(f"  Tags: {', '.join(tags)}")
    print("")

  return 0


def cmd_component_get(args: argparse.Namespace) -> int:
  """Displays details and source of a specific component."""
  corgi_dir = os.path.abspath(args.corgi_dir or ".corgi")
  renderer_inst = renderer.CorgiRenderer(corgi_dir)
  comp = renderer_inst.get_component(args.component_id)

  if not comp:
    print(f"Error: Component '{args.component_id}' not found in catalog.", file=sys.stderr)
    return 1

  if args.json:
    print(json.dumps(comp, indent=2))
    return 0

  print(f"=== Component: {comp.get('name', args.component_id)} [{comp.get('id')}] ===")
  print(f"Category:    {comp.get('category', 'atom')}")
  print(f"Description: {comp.get('description', '')}")
  print(f"File Path:   {comp.get('file', 'inline')}")
  print("\nParameters Schema:")
  for inp in comp.get("inputs_spec", []):
    print(f"  - ${inp.get('name')} [{inp.get('type', 'string')}]: {inp.get('description', '')} (default: {inp.get('default')})")

  print("\nParameterized Source Template:")
  print("-" * 50)
  print(comp.get("html_content", "").strip())
  print("-" * 50)
  return 0


def cmd_component_search(args: argparse.Namespace) -> int:
  """Searches components matching a query string."""
  corgi_dir = os.path.abspath(args.corgi_dir or ".corgi")
  renderer_inst = renderer.CorgiRenderer(corgi_dir)
  components = renderer_inst.catalog.get("components", {})
  query = args.query.lower()

  matches = []
  for comp_id, comp in components.items():
    search_space = (
        comp_id.lower()
        + " "
        + comp.get("name", "").lower()
        + " "
        + comp.get("description", "").lower()
        + " "
        + " ".join(comp.get("tags", [])).lower()
    )
    if query in search_space:
      matches.append((comp_id, comp))

  print(f"Search results for '{args.query}' ({len(matches)} matches):")
  for comp_id, comp in matches:
    print(f"  [{comp.get('category', 'atom')}] {comp_id}: {comp.get('name')} - {comp.get('description')}")

  return 0


def cmd_page_render(args: argparse.Namespace) -> int:
  """Renders a declarative page specification file to HTML."""
  page_file = os.path.abspath(args.page_file)
  if not os.path.exists(page_file):
    print(f"Error: Page config file '{page_file}' does not exist.", file=sys.stderr)
    return 1

  corgi_dir = os.path.abspath(args.corgi_dir or os.path.dirname(os.path.dirname(page_file)))
  page_config = _load_yaml_or_json(page_file)

  renderer_inst = renderer.CorgiRenderer(corgi_dir)
  html_output = renderer_inst.render_page(page_config)

  if args.output:
    out_file = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
      f.write(html_output)
    print(f"Rendered page written to: {out_file}")
  else:
    print(html_output)

  return 0


def cmd_page_validate(args: argparse.Namespace) -> int:
  """Validates a page config or catalog components for a11y, responsiveness, and schema integrity."""
  page_file = os.path.abspath(args.page_file)
  corgi_dir = os.path.abspath(args.corgi_dir or os.path.dirname(os.path.dirname(page_file)))

  val = validator.CorgiValidator()
  renderer_inst = renderer.CorgiRenderer(corgi_dir)
  page_config = _load_yaml_or_json(page_file)

  res = val.validate_page_config(page_config, renderer_inst.catalog)

  print(f"Validating Page: {page_file}")
  if res.errors:
    print("\n❌ Errors found:")
    for err in res.errors:
      print(f"  - {err}")
  if res.warnings:
    print("\n⚠️ Warnings:")
    for w in res.warnings:
      print(f"  - {w}")
  if res.suggestions:
    print("\n💡 Suggestions:")
    for s in res.suggestions:
      print(f"  - {s}")

  if res.is_valid and not res.warnings:
    print("\n✅ Page configuration is valid and all checks passed!")
    return 0
  return 1 if not res.is_valid else 0


def cmd_preview(args: argparse.Namespace) -> int:
  """Starts a local HTTP server to preview components and pages."""
  corgi_dir = os.path.abspath(args.corgi_dir or ".corgi")
  port = args.port
  host = args.host

  class CorgiPreviewHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
      parsed = urllib.parse.urlparse(self.path)
      path = parsed.path

      renderer_inst = renderer.CorgiRenderer(corgi_dir)

      if path in ("/", "/catalog"):
        # Serve Component Catalog Explorer UI
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

        comps = renderer_inst.catalog.get("components", {})
        cards_html = []
        for c_id, c in comps.items():
          try:
            rendered_sample = renderer_inst.render_component(c_id, {})
          except Exception as e:
            rendered_sample = f"<!-- Render preview error: {e} -->"

          cards_html.append(f"""
          <div class="bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-2xl p-6 shadow-sm mb-6">
            <div class="flex items-center justify-between mb-3 border-b border-gray-100 dark:border-zinc-800 pb-3">
              <div>
                <span class="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-300 mr-2">{c.get('category')}</span>
                <span class="font-bold text-gray-900 dark:text-white text-base">{c.get('name')}</span>
                <code class="text-xs bg-gray-100 dark:bg-zinc-800 px-2 py-0.5 rounded ml-2 text-gray-600 dark:text-zinc-300">{c_id}</code>
              </div>
            </div>
            <p class="text-xs text-gray-600 dark:text-zinc-400 mb-4">{c.get('description')}</p>
            <div class="p-4 bg-gray-50 dark:bg-zinc-950 rounded-xl border border-dashed border-gray-200 dark:border-zinc-800">
              {rendered_sample}
            </div>
          </div>
          """)

        empty_hint = """
        <div class="p-8 text-center bg-white dark:bg-zinc-900 rounded-2xl border border-dashed border-gray-300 dark:border-zinc-700">
          <h3 class="text-lg font-bold text-gray-800 dark:text-zinc-200">Catalog is currently empty</h3>
          <p class="text-xs text-gray-500 mt-2">The agent creates or scans components (structure, atoms, molecules) into .corgi/catalog.json.</p>
        </div>
        """ if not comps else ""

        body_html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CORGI Component Catalog Explorer</title>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-100 dark:bg-zinc-950 text-gray-900 dark:text-zinc-100 p-8">
  <div class="max-w-5xl mx-auto">
    <div class="flex items-center justify-between mb-8 pb-4 border-b border-gray-200 dark:border-zinc-800">
      <div>
        <h1 class="text-3xl font-extrabold flex items-center gap-3">
          <span>🐶</span> CORGI Component Catalog
        </h1>
        <p class="text-sm text-gray-500 mt-1">Catalog-driven Orchestration of Responsive Graphical Interfaces</p>
      </div>
      <a href="/pages/home" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg shadow-sm">View Home Page Preview</a>
    </div>
    {empty_hint}
    {''.join(cards_html)}
  </div>
</body>
</html>"""
        self.wfile.write(body_html.encode("utf-8"))
        return

      if path.startswith("/pages/"):
        raw_page_name = path[len("/pages/"):]
        page_name = os.path.basename(urllib.parse.unquote(raw_page_name))
        if not page_name or ".." in raw_page_name:
          self.send_error(400, "Invalid page name")
          return

        pages_dir = os.path.join(corgi_dir, "pages")
        page_file_yaml = os.path.join(pages_dir, f"{page_name}.yaml")
        page_file_json = os.path.join(pages_dir, f"{page_name}.json")

        target_file = page_file_yaml if os.path.exists(page_file_yaml) else page_file_json
        if (
            os.path.exists(target_file)
            and os.path.commonpath(
                [os.path.abspath(target_file), os.path.abspath(pages_dir)]
            )
            == os.path.abspath(pages_dir)
        ):
          self.send_response(200)
          self.send_header("Content-Type", "text/html; charset=utf-8")
          self.end_headers()
          cfg = _load_yaml_or_json(target_file)
          page_html = renderer_inst.render_page(cfg)
          self.wfile.write(page_html.encode("utf-8"))
          return

      self.send_error(404, "Page or component not found")

  print(f"Starting CORGI preview server on http://{host}:{port}")
  print(f"Catalog URL: http://{host}:{port}/catalog")
  print(f"Home Page:   http://{host}:{port}/pages/home")
  with socketserver.TCPServer((host, port), CorgiPreviewHandler) as httpd:
    try:
      httpd.serve_forever()
    except KeyboardInterrupt:
      print("\nShutting down preview server.")
  return 0


def main() -> int:
  parser = argparse.ArgumentParser(
      prog="corgi",
      description="CORGI CLI - Catalog-driven Orchestration of Responsive Graphical Interfaces.",
  )
  parser.add_argument("--corgi_dir", help="Path to .corgi directory", default=".corgi")
  subparsers = parser.add_subparsers(dest="command", required=True)

  # init
  p_init = subparsers.add_parser("init", help="Initialize .corgi workspace.")
  p_init.add_argument("--path", default=".", help="Root directory to initialize")
  p_init.add_argument("--theme_name", help="Custom theme name")
  p_init.add_argument("--primary_color", help="Primary brand color hex code")
  p_init.set_defaults(func=cmd_init)

  # component
  p_comp = subparsers.add_parser("component", help="Manage catalog components.")
  comp_sub = p_comp.add_subparsers(dest="subcommand", required=True)

  p_comp_list = comp_sub.add_parser("list", help="List catalog components.")
  p_comp_list.add_argument("--category", choices=["all", "structure", "atom", "molecule"], default="all")
  p_comp_list.set_defaults(func=cmd_component_list)

  p_comp_add = comp_sub.add_parser("add", help="Register a new component in the catalog.")
  p_comp_add.add_argument("--id", required=True, help="Component ID")
  p_comp_add.add_argument("--category", choices=["structure", "atom", "molecule"], required=True, help="Category")
  p_comp_add.add_argument("--name", help="Human-readable component name")
  p_comp_add.add_argument("--description", help="Description of what this component is used for")
  p_comp_add.add_argument("--file", help="Path to existing HTML template file")
  p_comp_add.add_argument("--template", help="Inline HTML template string")
  p_comp_add.add_argument("--inputs", help="JSON array of inputs_spec objects")
  p_comp_add.add_argument("--tags", help="Comma-separated tags")
  p_comp_add.set_defaults(func=cmd_component_add)

  p_comp_get = comp_sub.add_parser("get", help="Get component details and source.")
  p_comp_get.add_argument("component_id", help="Component ID")
  p_comp_get.add_argument("--json", action="store_true", help="Output in JSON format")
  p_comp_get.set_defaults(func=cmd_component_get)

  p_comp_search = comp_sub.add_parser("search", help="Search components.")
  p_comp_search.add_argument("query", help="Search query")
  p_comp_search.set_defaults(func=cmd_component_search)

  # page
  p_page = subparsers.add_parser("page", help="Manage and render pages.")
  page_sub = p_page.add_subparsers(dest="subcommand", required=True)

  p_page_render = page_sub.add_parser("render", help="Render YAML/JSON page config to HTML.")
  p_page_render.add_argument("page_file", help="Path to page.yaml or page.json")
  p_page_render.add_argument("--output", help="Output HTML file path (prints to stdout if omitted)")
  p_page_render.set_defaults(func=cmd_page_render)

  p_page_validate = page_sub.add_parser("validate", help="Validate page config for a11y, responsiveness, and contracts.")
  p_page_validate.add_argument("page_file", help="Path to page.yaml or page.json")
  p_page_validate.set_defaults(func=cmd_page_validate)

  # preview
  p_preview = subparsers.add_parser("preview", help="Start local preview HTTP server.")
  p_preview.add_argument("--port", type=int, default=3000, help="Port to listen on (default: 3000)")
  p_preview.add_argument("--host", default="0.0.0.0", help="Host interface to bind to")
  p_preview.set_defaults(func=cmd_preview)

  args = parser.parse_args()
  return args.func(args)


if __name__ == "__main__":
  sys.exit(main())
