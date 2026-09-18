# CORGI Catalog & Configuration Schema Specification

The `.corgi/` directory is the single source of truth for all UI design systems,
component templates, declarative page definitions, and rendering configurations.

---

## Directory Structure

```
<project_root>/
└── .corgi/
    ├── catalog.json             # Master index of all registered components
    ├── layout.html              # Global HTML layout template
    ├── theme.json               # Design tokens (colors, typography, radii, spacing)
    ├── assets.json              # Static asset URLs, icons, and CDN links
    ├── cms_render.<ext>         # Native project render engine (e.g. .tsx, .dart, .py)
    ├── components/
    │   ├── structure/           # Grids, column layouts, containers, sections
    │   │   ├── hero_section.html
    │   │   ├── two_column_grid.html
    │   │   └── three_column_grid.html
    │   ├── atoms/               # Buttons, inputs, badges, avatars, spans
    │   │   ├── primary_button.html
    │   │   ├── secondary_button.html
    │   │   ├── text_input.html
    │   │   └── pill_badge.html
    │   └── molecules/           # Composite cards, forms, headers, modals
    │       ├── profile_card.html
    │       ├── spotlight_banner.html
    │       ├── stats_card.html
    │       ├── navbar.html
    │       └── footer.html
    └── pages/                   # Declarative YAML/JSON page specifications
        ├── home.yaml
        ├── dashboard.yaml
        └── settings.yaml
```

---

## 1. `catalog.json` Schema

The `catalog.json` file registers all components, categorizing them into `structure`, `atom`, or `molecule`, along with their parameter specifications.

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "version": "1.0.0",
  "description": "CORGI UI Component Catalog",
  "components": {
    "profile_card": {
      "id": "profile_card",
      "name": "User Profile Card",
      "category": "molecule",
      "description": "Displays user avatar, name, title, and team badge in a responsive card.",
      "file": "components/molecules/profile_card.html",
      "inputs_spec": [
        {
          "name": "name",
          "type": "string",
          "default": "Jane Doe",
          "description": "Full name of the user"
        },
        {
          "name": "avatar_url",
          "type": "string",
          "default": "https://lh3.googleusercontent.com/a/default-user",
          "description": "URL to user's avatar image"
        },
        {
          "name": "designation",
          "type": "string",
          "default": "Software Engineer",
          "description": "Job title or role"
        },
        {
          "name": "team",
          "type": "string",
          "default": "Engineering",
          "description": "Team or department"
        }
      ],
      "tags": ["card", "user", "profile", "employee"]
    }
  }
}
```

---

## 2. Global Layout Template (`layout.html`)

Defines global head meta, typography (e.g. Google Sans), theme tokens, headers, and footers.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${PAGE_TITLE}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, sans-serif; }
  </style>
</head>
<body class="bg-gray-50 dark:bg-zinc-950 text-gray-900 dark:text-zinc-100 min-h-screen flex flex-col antialiased">
  <header class="sticky top-0 z-50 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border-b border-gray-200 dark:border-zinc-800">
    ${NAVBAR}
  </header>

  <main class="flex-grow max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-12">
    ${PAGE_CONTENT}
  </main>

  <footer class="bg-white dark:bg-zinc-900 border-t border-gray-200 dark:border-zinc-800 py-8">
    ${FOOTER}
  </footer>
</body>
</html>
```

---

## 3. Theme Tokens (`theme.json`)

```json
{
  "theme_name": "Fleet Modern",
  "version": "1.0.0",
  "colors": {
    "primary": "#1a73e8",
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
```

---

## 4. Declarative Page Specs (`pages/*.yaml`)

Pages are expressed as trees of components and parameter values:

```yaml
page_id: team_portal
title: Team Directory
layout_id: default
navbar:
  component_id: navbar
  params:
    brand_name: "Floe Engineering"
    nav_links:
      - label: "Directory"
        url: "/directory"
      - label: "Docs"
        url: "/docs"

components:
  - component_id: hero_section
    params:
      title: "Meet the Team"
      subtitle: "Engineers, researchers, and designers building the future."
      badge:
        component_id: pill_badge
        params:
          text: "Floe 2026"
      cta_button:
        component_id: primary_button
        params:
          label: "View Open Roles"
          url: "/careers"

  - component_id: two_column_grid
    params:
      col_content:
        - component_id: profile_card
          params:
            name: "Khyati Mahendru"
            avatar_url: "https://lh3.googleusercontent.com/a/default-user"
            designation: "Staff Software Engineer"
            team: "Corp Eng Floe Agents"
```
