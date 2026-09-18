# Accessibility (a11y) and Mobile-First Responsive Design Standards

Every component generated or modified in the CORGI catalog must comply with strict accessibility standards (WCAG 2.1 AA) and mobile-first responsive design principles.

---

## 1. Accessibility (a11y) Rules

### Rule 1: Semantic HTML First
- Always use `<header>`, `<nav>`, `<main>`, `<section>`, `<article>`, `<footer>` rather than generic `<div>` tags where appropriate.
- Heading hierarchy must be sequential: `<h1>` (one per page) -> `<h2>` -> `<h3>` without skipping levels.

### Rule 2: Image Alternatives (`alt`)
- Every `<img>` tag MUST have an `alt` attribute.
- For informative images: `alt="${image_alt}"` or descriptive text.
- For purely decorative images: `alt=""` and `aria-hidden="true"`.

### Rule 3: Accessible Interactive Elements
- Buttons must have visible text or an explicit `aria-label`:
  ```html
  <!-- BAD: Screen reader cannot tell what this button does -->
  <button class="p-2"><span class="material-symbols-outlined">close</span></button>

  <!-- GOOD: Fully accessible -->
  <button class="p-2" aria-label="Close dialog">
    <span class="material-symbols-outlined" aria-hidden="true">close</span>
  </button>
  ```
- Links must indicate destination context (avoid vague text like "click here").

### Rule 4: Form Controls and Labels
- All `<input>`, `<select>`, and `<textarea>` elements must have an associated `<label for="...">` or `aria-label="..."`.

### Rule 5: Focus Indicators and Keyboard Navigation
- All interactive elements must maintain clear focus rings:
  `focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2`.

---

## 2. Mobile-First Responsive Design Rules

### Rule 1: Never Hardcode Desktop Fixed Widths
- ❌ **Forbidden**: `style="width: 960px;"`, `w-[960px]`, `min-w-[800px]`.
- ✅ **Required**: `w-full max-w-5xl mx-auto px-4 sm:px-6 lg:px-8`.

### Rule 2: Mobile-First Multi-Column Layouts
- All multi-column grids must start with a single column on small viewports and scale up at standard breakpoints:
  ```html
  <!-- 1 column on mobile, 2 on tablet, 3 on desktop -->
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
    ${cards}
  </div>
  ```

### Rule 3: Breakpoint Conventions (Tailwind CSS)
- `sm:` `>= 640px` (Tablets / large phones in landscape)
- `md:` `>= 768px` (Tablets in portrait / small laptops)
- `lg:` `>= 1024px` (Laptops / desktops)
- `xl:` `>= 1280px` (Large monitors)

### Rule 4: Flexible Typography and Spacing
- Use clamp or responsive typography utilities:
  `text-3xl sm:text-4xl md:text-5xl`.
- Use fluid padding on page containers:
  `py-8 md:py-16 px-4 sm:px-6 lg:px-8`.

---

## Automated Validation

CORGI includes an automated validator that audits these rules:

```bash
corgi page validate .corgi/pages/home.yaml
```
Fix all errors and warnings before submitting code or publishing page configurations.
