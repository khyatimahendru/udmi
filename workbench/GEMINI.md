# UDMI Workbench UI Development Guidelines

This document defines the architectural rules, UX engineering standards, and workflow principles for building the next-generation **UDMI Workbench UI** using CORGI (Catalog-driven Orchestration of Responsive Graphical Interfaces) design principles.

---

## 1. Core Principles & Philosophy

1. **Strict Contract Compliance**:
   - All frontend and integration code must strictly implement the 5 canonical contracts defined in [`workbench/WORKBENCH_CONTRACTS.md`](./WORKBENCH_CONTRACTS.md).
   - No legacy regressions: **Zero `<iframe>` elements, zero `postMessage` synchronization, and no monolithic process supervisors**.
2. **MCP-First Determinism**:
   - All deterministic backend operations (environment control, test execution, schema reading, device queries) must go through standard Model Context Protocol (MCP JSON-RPC 2.0) via `mcp/server.py`.

---

## 2. CORGI UX Framework Standards

All UI development in `workbench/` must follow the CORGI atomic hierarchy and catalog-driven design:

### 2.1. Atomic Hierarchy
* **Design Tokens (`theme.css` / tokens)**:
  - Material 3 elevation surfaces (`--bg-surface-container-low`, `--bg-surface-high`).
  - Strict semantic colors: Pass (Green `#10b981`), Fail (Red `#ef4444`), Warning/Contributing (Amber `#f59e0b`), Unresolved (Blue `#3b82f6`), Neutral (Gray `#6b7280`).
  - Standard typography tokens (Inter / Roboto for UI, Roboto Mono / JetBrains Mono for code, logs, and trace diffs).
* **Atoms**:
  - Buttons (`M3Button`: Filled, Tonal, Outlined, Icon-only).
  - Badges & Chips (`StatusBadge`: `PRIMARY`, `CONTRIBUTING`, `REFUTED`, `UNRESOLVED`, `PASSED`, `FAILED`).
  - Form Inputs (`M3Input`, `M3Select`, `M3Toggle`).
* **Molecules**:
  - `ToolCallBadge`: Collapsible tool execution chip displaying tool name, input params, duration, and output preview.
  - `ThoughtAccordion`: Collapsible reasoning disclosure displaying internal model thinking and phase transitions (`Actor -> Critic -> Arbitrator`).
  - `MetricCard`: KPI summaries (compliance score %, total devices, pass rate, flakiness index).
  - `SearchBar`: Log & device filtering with keyboard shortcuts (`/`).
* **Organisms**:
  - `DiagnosticDrawer`: Multi-turn conversational streaming feed with live token rendering, thought disclosure, and tool badges.
  - `HypothesisMatrix`: Interactive table comparing competing failure hypotheses with evidence-tier tags (`LOCAL_FILE`, `CLOUD`, `NONE`).
  - `ComplianceGrid`: Device x Test compliance matrix with sorting, filtering, and instant triage triggering.
  - `TestbedCanvas`: Interactive SVG/DOT topology viewer with node inspection and live connection states.
  - `LogTerminal`: High-performance, virtualized terminal viewer streaming live tmux pane buffers.
* **Templates & Pages**:
  - `/assistant`: Dedicated full-page general UDMI assistant workspace.
  - `/triage/:sessionId`: Focused diagnostic investigation workspace for test failures.
  - `/testbed`: Testbed and Cadre local stack manager.
  - `/compliance`: Curated compliance matrix and scorecard.
  - `/devices/:deviceId`: Device metadata, points, and message trace explorer.
  - `/catalog`: Curated menu of approved IoT devices.

### 2.2. Component Cataloging Rule
* Every new atom, molecule, or organism must have:
  1. A declarative property schema (e.g. TypeScript interface or JSON/YAML config).
  2. Clear state variations: `default`, `hover`, `active`, `focused`, `disabled`, `loading`, `error`.
  3. No tight coupling to UDMI business logic; pass data via props/slots so the component is pure and reusable.
* When a component reaches production quality, document its schema and add it to the Workbench component catalog.

---

## 3. Route-Driven Architecture & State Rules

1. **First-Class URLs (No Monolithic Single-Screen Bloat)**:
   - Every primary view must have a direct, bookmarkable URL.
   - Full support for multi-tab workflows: an operator must be able to open `/testbed` on Monitor 1 and `/compliance` on Monitor 2 simultaneously.
2. **Client-Side Routing (No Traditional Page Reloads)**:
   - View transitions must occur client-side without full-page document reloads.
   - Long-running SSE streams (Mantis reasoning loops, live sequencer test logs) must remain alive in memory when navigating between routes.
3. **Global Assistant Drawer (`Cmd+K` / `Ctrl+K`)**:
   - Mantis must be summonable as a slide-out drawer from any screen.
   - **Context Inheritance**:
     - From `/devices/AHU-1` → Drawer automatically sets `activeDevice = 'AHU-1'`.
     - From `/compliance` → Drawer automatically sets active `siteModel`.
     - From `/assistant` or standalone → Drawer operates in General Exploration Mode.

---

## 4. Backend Integration Invariants (The 5 Contracts)

* **Contract 1 (MCP JSON-RPC)**:
  - Do NOT create ad-hoc HTTP endpoints in custom servers.
  - Call tools deterministically via `POST /message` or `POST /rpc` using standard JSON-RPC 2.0:
    ```json
    {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "inspect_site_model", "arguments": {"site_model": "sites/udmi_site_model"}}}
    ```
* **Contract 2 (Mantis Streaming Agent)**:
  - Connect to `POST /api/mantis/chat` via Server-Sent Events (`text/event-stream`).
  - Handle all canonical event types: `phase`, `thought`, `token`, `tool_call`, `tool_result`, `hypothesis_matrix`, `diagram`, `done`, `error`.
  - Support slash commands: `/status`, `/logs <window>`, `/clear`, `/export`, `/help`.
* **Contract 3 (Real-Time Logs)**:
  - Stream live console output from tmux window buffers via `GET /api/logs/stream?session_id=...&window=...`.
  - Handle stream reconnection gracefully with exponential backoff.
* **Contract 4 (Workspace State)**:
  - Maintain a centralized reactive state store conforming to `WorkspaceState` in `WORKBENCH_CONTRACTS.md`.
* **Contract 5 (Compliance & Reporting)**:
  - Use the standardized compliance matrix schema for scorecards and certification export bundles.

---

## 5. Professional UI/UX Standards

* **Accessibility (WCAG 2.1 AA)**:
  - Full keyboard navigability: `Tab` ordering, `Esc` to dismiss modals/drawers, `Cmd+K` for assistant.
  - Proper ARIA attributes: `aria-live="polite"` on streaming token containers, `aria-expanded` on accordions.
  - Minimum contrast ratio of 4.5:1 for normal text across light and dark themes.
* **Zero Layout Shifts & Viewport Locking**:
  - Fixed-viewport application layout (`100vh` / `100dvh`) with internal independent scrolling containers.
  - No double scrollbars or unwanted document-level scrolling.
* **Error Resilience & Fail Fast**:
  - Always surface actionable, technical error messages when MCP tools or API calls fail; do not swallow errors into empty states.
  - Visual loading skeletons and progress spinners during async operations.

---

## 6. Clean Architecture & Anti-Spaghetti Invariants

To prevent tight coupling, tangled state mutations, and unmaintainable "spaghetti code," the Workbench codebase enforces a **strict 4-layer unidirectional architecture**:

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Layer 1: Pure Presentation (components/, .corgi/)                          │
│ - Stateless Atoms, Molecules, Organisms                                    │
│ - Driven 100% by typed props & upward semantic event callbacks             │
│ - FORBIDDEN: fetch(), EventSource, direct store mutation, route awareness  │
└────────────────────────────────────▲───────────────────────────────────────┘
                                     │ Props down / Events up
┌────────────────────────────────────┴───────────────────────────────────────┐
│ Layer 2: Route Views & Reactive State Store (views/, store/)               │
│ - Route-level controllers (/assistant, /triage, /testbed, /compliance...)  │
│ - Central WorkspaceState store (Contract 4)                                │
│ - Orchestrates Layer 3 service clients and passes state to Layer 1         │
│ - FORBIDDEN: Raw HTTP/SSE protocol parsing, inline JSON-RPC formatting     │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ Typed Interface Calls
┌────────────────────────────────────▼───────────────────────────────────────┐
│ Layer 3: Contract Service Adapters (services/)                             │
│ - IMcpClient (Contract 1), IMantisStreamClient (Contract 2),               │
│   ILogStreamClient (Contract 3), IComplianceClient (Contract 5)            │
│ - Encapsulates JSON-RPC 2.0 envelopes, SSE parsing, retries & timeouts     │
│ - Validates wire payloads at the boundary before returning typed models    │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ HTTP / SSE + X-Correlation-ID
┌────────────────────────────────────▼───────────────────────────────────────┐
│ Layer 4: Backend Gateway & Domain Engines (server/, mcp/, mantis/)         │
│ - Thin HTTP/SSE transport adapters delegating to mcp/server.py & mantis/   │
│ - Zero UI presentation logic; strict Pydantic/JSON-Schema validation       │
└────────────────────────────────────────────────────────────────────────────┘
```

### 6.1. Structural & Dependency Rules
1. **Strict Downward Dependency Direction**:
   - `Layer 1 (Components)` may ONLY import design tokens and shared TypeScript data interfaces (`types/`).
   - `Layer 2 (Views/Store)` may import `Layer 1` components, `Layer 3` service interfaces, and `types/`. Views must NEVER import other views.
   - `Layer 3 (Services)` may ONLY import `types/` and the structured logger (`utils/logger`). Services must NEVER import UI components or view modules.
2. **Explicit Interface Contracts (Zero Leaky Abstractions)**:
   - Every external communication boundary must be backed by an explicit interface (`IMcpClient`, `IMantisStreamClient`, `ILogStreamClient`, `IComplianceService`) and dedicated domain types (`types/contracts.ts` mirroring `WORKBENCH_CONTRACTS.md`).
   - Using untyped `any` payloads, ad-hoc dictionary bags, or raw `fetch()` / `new EventSource()` inside components or views is strictly prohibited.
3. **Single-Responsibility Modules & File Size Guardrails**:
   - Each module must have a single, clear responsibility (one component per file, one contract client per service file, one slice/domain per store module).
   - No file may exceed **300 lines of code** without decomposing sub-components or helper modules.

---

## 7. Structured Logging & End-to-End Observability

Observability is a first-class architectural requirement across both the frontend SPA and backend gateway:

### 7.1. Unified Structured Log Schema
All logs across client and server must be emitted as structured records (never ad-hoc `console.log("here", data)` or `print()` statements):

```typescript
export interface LogEntry {
  timestamp: string;          // ISO-8601 UTC timestamp
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
  layer: 'UI' | 'STORE' | 'MCP_RPC' | 'MANTIS_SSE' | 'LOG_STREAM' | 'GATEWAY';
  correlationId: string;      // End-to-end trace ID (e.g. 'req-8f3a2b1c')
  module: string;             // e.g. 'McpClient', 'TriageView', 'WorkspaceStore'
  event: string;              // Canonical event name, e.g. 'rpc.call.start', 'sse.event.received'
  durationMs?: number;        // Execution latency for operations/requests
  context?: {
    sessionId?: string | null;
    deviceId?: string;
    testId?: string;
    toolName?: string;
  };
  details?: Record<string, unknown>;
  error?: {
    code: string;
    message: string;
    stack?: string;
  };
}
```

### 7.2. End-to-End Correlation Propagation (`X-Correlation-ID`)
1. **Origin Generation**: Every user-initiated action, MCP tool call, or Mantis chat request generates a unique `correlationId` (or uses the JSON-RPC `id`).
2. **Wire Propagation**: Layer 3 clients attach `X-Correlation-ID: <correlationId>` to all HTTP/SSE requests (`POST /rpc`, `POST /api/mantis/chat`, `GET /api/logs/stream`).
3. **Backend Echo & Tagging**: The backend gateway reads `X-Correlation-ID`, binds it to the request context logger, logs tool/agent execution duration and status with that ID, and returns `X-Correlation-ID` in the response headers and error payloads.

### 7.3. Mandatory Instrumentation Points
* **Contract 1 (MCP JSON-RPC)**: Log `rpc.call.start` (method, tool name, sanitized args) and `rpc.call.complete` / `rpc.call.error` (with `durationMs` and error code).
* **Contract 2 & 3 (SSE Streams)**: Log stream lifecycle transitions (`sse.connect`, `sse.phase_change`, `sse.reconnect_scheduled`, `sse.closed`, `sse.error`) without flooding the log buffer on individual text tokens.
* **Contract 4 (Workspace State Store)**: Log state transitions (`store.mutation`) with action name, previous/next summary diff, and triggering source.
* **Client-Side Diagnostic Ring Buffer**: The frontend `WorkbenchLogger` maintains a bounded in-memory ring buffer (last 1,000 structured entries) accessible via the developer diagnostics console and automatically included when exporting failure bundles (`/export`).

