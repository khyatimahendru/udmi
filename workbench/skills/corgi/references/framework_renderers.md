# Framework-Specific Deterministic Renderers

While the `.corgi/` configuration files (`catalog.json`, `pages/*.yaml`, `theme.json`) are language-agnostic, the **render function itself is written in the native framework and language of your project**.

When scaffolding or modifying an application, the Agent writes the appropriate deterministic `cms_render` module in the project's target language (e.g. React/TypeScript, Dart, Python, Go, Vue, Svelte, Kotlin, Lit, or any other stack).

> [!IMPORTANT]
> **Universal Framework Adaptation Rule**:
> The Agent is NOT limited to the languages listed below. For **any** language or framework chosen by the user, the Agent dynamically creates a `cms_render.<ext>` module adhering to the core pattern:
> 1. Ingest page configuration (JSON/YAML) and component catalog.
> 2. Recursively evaluate component trees and parameter bindings.
> 3. Deterministically output the native framework elements/templates without relying on runtime LLM generation.

---

## 1. React / TypeScript Renderer (`cms_render.tsx`)

In a React or Next.js application, the render function dynamically maps component IDs from `.corgi/pages/*.yaml` to parameterized React functional components.

```tsx
import React from 'react';
import catalogData from './.corgi/catalog.json';

// Component registry mapping catalog IDs to React components
const COMPONENT_REGISTRY: Record<string, React.FC<any>> = {
  hero_section: ({ title, subtitle, badge, cta_button }) => (
    <section className="text-center py-16 px-4 max-w-4xl mx-auto">
      {badge && <div className="mb-4">{renderNode(badge)}</div>}
      <h1 className="text-5xl font-extrabold text-gray-900 dark:text-white tracking-tight mb-4">
        {title}
      </h1>
      <p className="text-lg text-gray-600 dark:text-zinc-400 mb-8">{subtitle}</p>
      {cta_button && <div>{renderNode(cta_button)}</div>}
    </section>
  ),

  two_column_grid: ({ col_content }) => (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 my-8">
      {Array.isArray(col_content) ? col_content.map((item, idx) => (
        <React.Fragment key={idx}>{renderNode(item)}</React.Fragment>
      )) : renderNode(col_content)}
    </div>
  ),

  profile_card: ({ name, avatar_url, designation, team }) => (
    <div className="p-6 bg-white dark:bg-zinc-900 rounded-2xl border border-gray-200 dark:border-zinc-800 shadow-sm flex items-center gap-4">
      <img src={avatar_url} alt={name} className="w-14 h-14 rounded-full object-cover" />
      <div>
        <h3 className="text-base font-bold text-gray-900 dark:text-zinc-100">{name}</h3>
        <p className="text-xs font-medium text-blue-600 dark:text-blue-400">{designation}</p>
        <p className="text-xs text-gray-500 dark:text-zinc-400">{team}</p>
      </div>
    </div>
  ),

  primary_button: ({ label, url }) => (
    <a href={url} className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm shadow-sm transition">
      {label}
    </a>
  ),
};

export function renderNode(node: { component_id: string; params?: Record<string, any> } | string): React.ReactNode {
  if (!node) return null;
  if (typeof node === 'string') return node;
  const Component = COMPONENT_REGISTRY[node.component_id];
  if (!Component) {
    return <div className="text-red-500 text-xs">Unknown component: {node.component_id}</div>;
  }
  return <Component {...(node.params || {})} />;
}

export function CmsPage({ pageConfig }: { pageConfig: { title: string; components: any[] } }) {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-zinc-950 text-gray-900 dark:text-zinc-100">
      <main className="max-w-7xl mx-auto px-4 py-8">
        {pageConfig.components.map((comp, idx) => (
          <React.Fragment key={idx}>{renderNode(comp)}</React.Fragment>
        ))}
      </main>
    </div>
  );
}
```

---

## 2. Dart / Flutter / AngularDart Renderer (`cms_render.dart`)

In a Dart web or Flutter application, the deterministic renderer maps component definitions to Widget or Angular component trees.

```dart
import 'package:flutter/material.dart';

Widget renderNode(Map<String, dynamic> node) {
  final componentId = node['component_id'] as String?;
  final params = (node['params'] as Map<String, dynamic>?) ?? {};

  switch (componentId) {
    case 'hero_section':
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 32.0, horizontal: 16.0),
        child: Column(
          children: [
            Text(
              params['title'] ?? '',
              style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            Text(
              params['subtitle'] ?? '',
              style: const TextStyle(fontSize: 16, color: Colors.grey),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      );

    case 'profile_card':
      return Card(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        child: ListTile(
          leading: CircleAvatar(
            backgroundImage: NetworkImage(params['avatar_url'] ?? ''),
          ),
          title: Text(params['name'] ?? '', style: const TextStyle(fontWeight: FontWeight.bold)),
          subtitle: Text('${params['designation']} • ${params['team']}'),
        ),
      );

    case 'two_column_grid':
      final items = (params['col_content'] as List<dynamic>?) ?? [];
      return LayoutBuilder(
        builder: (context, constraints) {
          int crossAxisCount = constraints.maxWidth > 600 ? 2 : 1;
          return GridView.count(
            crossAxisCount: crossAxisCount,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            children: items.map((item) => renderNode(item as Map<String, dynamic>)).toList(),
          );
        },
      );

    default:
      return Text('Unknown component: $componentId', style: const TextStyle(color: Colors.red));
  }
}
```

---

## 3. Python / Flask / Soy Renderer (`cms_render.py`)

In Python backends (such as Flask, Django, or Google3 Soy templates), the renderer performs deterministic string/template substitution:

```python
import json
import os
from typing import Any

class CmsRenderer:
  def __init__(self, corgi_dir: str = ".corgi"):
    self.corgi_dir = corgi_dir
    with open(os.path.join(corgi_dir, 'catalog.json'), 'r') as f:
      self.catalog = json.load(f)

  def render_page(self, page_config: dict[str, Any]) -> str:
    rendered_parts = []
    for comp_ref in page_config.get('components', []):
      comp_id = comp_ref.get('component_id')
      params = comp_ref.get('params', {})
      rendered_parts.append(self.render_component(comp_id, params))
    
    with open(os.path.join(self.corgi_dir, 'layout.html'), 'r') as f:
      layout_html = f.read()
    
    return layout_html.replace('${PAGE_CONTENT}', '\n'.join(rendered_parts)).replace('${PAGE_TITLE}', page_config.get('title', ''))

  def render_component(self, comp_id: str, params: dict[str, Any]) -> str:
    comp_def = self.catalog.get('components', {}).get(comp_id)
    if not comp_def:
      return f'<!-- Unknown component {comp_id} -->'
    
    template_path = os.path.join(self.corgi_dir, comp_def['file'])
    with open(template_path, 'r') as f:
      html = f.read()
    
    for k, v in params.items():
      if isinstance(v, dict) and 'component_id' in v:
        sub_html = self.render_component(v['component_id'], v.get('params', {}))
        html = html.replace(f'${{{k}}}', sub_html)
      elif isinstance(v, list):
        sub_items = [self.render_component(item['component_id'], item.get('params', {})) for item in v if isinstance(item, dict) and 'component_id' in item]
        html = html.replace(f'${{{k}}}', '\n'.join(sub_items))
      else:
        html = html.replace(f'${{{k}}}', str(v))
    return html
```

---

## Summary of Framework Flexibility

| Target Stack | Renderer File | Rendering Mechanism |
| :--- | :--- | :--- |
| **React / Next.js** | `cms_render.tsx` | Component Registry map -> JSX Element Tree |
| **Dart / Flutter** | `cms_render.dart` | Factory switch -> Widget / Element Tree |
| **Angular / TypeScript**| `cms_render.ts` | Dynamic Component Loader (`ViewContainerRef`) |
| **Python / Soy** | `cms_render.py` | String & template substitution with Soy sanitization |
| **Go** | `cms_render.go` | `html/template` pipeline |
| **Vue / Svelte** | `cms_render.<ext>` | Native Dynamic Component Rendering |

The `.corgi/` contracts remain identical across all frameworks, ensuring teams can switch or share catalogs effortlessly!
