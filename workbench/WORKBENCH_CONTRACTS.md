# UDMI Workbench: Architecture & Interface Contracts Specification

**Document Version**: 1.0.0  
**Status**: Canonical Production Specification  
**Reference Document**: [Mantis Shrimp Scoping Doc (Google Docs)](https://docs.google.com/document/d/1LotYECAoFi8pbAIGmihNrqCEHiNTiwTqldSv1JjfXv8/edit?tab=t.0#heading=h.6pkqe3kam9rb)  
**Package Target**: `workbench/` (Unified Next-Gen Workbench UI & Backend Integration)

---

## 1. Executive Summary & Vision

The **Mantis Shrimp** vision converges three foundational evolutions of UDMI device testing into a unified product:
1. **Mantis Workbench**: LLM-assisted diagnostic reasoning for device developers to understand *why* tests fail and how to fix them.
2. **Test Cadre**: A reproducible, standalone, containerized/local test infrastructure for test lab operators to run automated compliance suites horizontally across multiple devices without external cloud dependencies.
3. **Unified Product**: Standardized reporting and hardware cataloging for ecosystem curators to certify and maintain an approved menu of production-ready IoT devices.

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 MANTIS SHRIMP VISION                   │
                  └──────────────────────────┬─────────────────────────────┘
                                             │
             ┌───────────────────────────────┼──────────────────────────────┐
             ▼                               ▼                              ▼
   ┌───────────────────┐           ┌───────────────────┐          ┌───────────────────┐
   │ Mantis Workbench  │           │    Test Cadre     │          │  Unified Product  │
   │ - Assisted Diag   │           │ - Horizontal Lab  │          │ - Device Catalog  │
   │ - Root Cause RCA  │           │ - Standalone Mock │          │ - Compliance Score│
   │ - Dev Remediation │           │ - Swappable Stack │          │ - Curated Menu    │
   └─────────┬─────────┘           └─────────┬─────────┘          └─────────┬─────────┘
             │                               │                              │
             ▼                               ▼                              ▼
      Device Developer               Test Lab Operator              Ecosystem Curator
      (Deep-dive 1 DUT)              (Broad multi-DUT)              (Certify & catalog)
```

### Architectural Foundation: The MCP-First Design
The Workbench architecture is cleanly decoupled into two backend planes and a single-page frontend application:
- **`mcp/server.py`** provides the standard **Model Context Protocol (JSON-RPC 2.0)** over stdio and HTTP/SSE for all deterministic operations, environment provisioning, and data inspections.
- **`mantis/`** provides the multi-tier **Streaming AI Agent (SSE)** for autonomous triage and interactive troubleshooting.
- **The Frontend UI** is a modern, single-page application (SPA) interacting with the backend purely through **5 canonical contracts**.

---

## 2. The 3 Primary User Personas & Workflows

| Persona | Core Mission | Key UI Needs | Primary Contracts Used |
| :--- | :--- | :--- | :--- |
| **Device Developer** | Develop and validate a specific IoT device before deployment. | Deep-dive failure triage, schema inspection, state-sync timelines, live writeback validation, automated code/config remediation. | Contract 2 (Agent SSE), Contract 1 (MCP Tools), Contract 4 (Workspace State) |
| **Test Lab Operator** | Manage physical/virtual test rigs, execute suites across many units. | Standalone local stack setup (`//mqtt/localhost:18833`), swappable services (`-x udmis`, `-a validator`), live multi-window tmux logs, ATN control. | Contract 1 (Infrastructure Control), Contract 3 (Log Streaming), Contract 4 (Workspace State) |
| **Ecosystem Curator** | Certify devices and maintain an approved catalog for installations. | Standardized compliance matrices, exportable test packages, flakiness indices, benchmark comparisons. | Contract 5 (Compliance & Reporting), Contract 1 (Catalog & Artifact Inspection) |

---

## 3. High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                   Workbench UI (SPA)                                    │
│                   (Single-Page Application: React / Svelte / Web Components)            │
│  ┌───────────────────────────┐ ┌───────────────────────────┐ ┌────────────────────────┐ │
│  │   Testbed & Cadre View    │ │  Compliance Matrix View   │ │   Mantis Triage Drawer │ │
│  │  - Swappable Stack Ctrl   │ │  - Device x Test Grid     │ │  - Tripartite Reasoner │ │
│  │  - ATN Writeback Peer     │ │  - Flakiness & KPI Scores │ │  - Live Thought Accord │ │
│  │  - Live Tmux Terminal     │ │  - Standardized Export    │ │  - Hypothesis Matrix   │ │
│  └─────────────┬─────────────┘ └─────────────┬─────────────┘ └───────────┬────────────┘ │
│                │                             │                           │              │
│                └──────────────────────┐      │      ┌────────────────────┘              │
│                                       ▼      ▼      ▼                                   │
│                           ┌────────────────────────────────────────┐                    │
│                           │      Client State Store (Contract 4)   │                    │
│                           │  - siteModel, activeDevice, activeTest │                    │
│                           │  - projectSpec, sessionId, setupMode   │                    │
│                           └──────────────────┬─────────────────────┘                    │
└──────────────────────────────────────────────┼──────────────────────────────────────────┘
                                               │
     ┌─────────────────────────────────────────┼────────────────────────────────────────┐
     │ 1. MCP Tool Calls (JSON-RPC)            │ 2. Agent SSE Stream    │ 3. Log Stream │
     │ (POST /message or POST /rpc)            │ (POST /api/mantis/chat)│ (GET /logs/..)│
     ▼                                         ▼                        ▼               ▼
┌───────────────────────────────┐ ┌─────────────────────────┐ ┌─────────────────────────┐
│     MCP Server & Registry     │ │      Mantis Engine      │ │   Session & Tmux Gateway│
│       (mcp/server.py)         │ │    (mantis/agent.py)    │ │(mcp/session_manager.py) │
│ - 20+ Canonical Tools         │ │ - Actor (Flash ReAct)   │ │ - Isolated tmux sessions│
│ - Site Model & Schema Read    │ │ - Critic (Pro Audit)    │ │ - User ports (18833,...)│
│ - Graphviz DOT -> SVG         │ │ - Arbitrator (Synthesis)│ │ - Buffer Capture        │
└───────────────┬───────────────┘ └────────────┬────────────┘ └────────────┬────────────┘
                │                              │                           │
                └──────────────────────────────┴───────────────────────────┘
                                               │
                                               ▼
                              ┌──────────────────────────────────┐
                              │       Local Substrate / DUT      │
                              │  - Mosquitto, etcd, InfluxDB     │
                              │  - PostgreSQL, UDMIS             │
                              │  - DUT (Physical / Pubber)       │
                              │  - Ancillary Test Node (ATN)     │
                              └──────────────────────────────────┘
```

### 3.1. Route-Driven Application Hierarchy

Workbench is structured as a route-driven application where every view and capability has a first-class, bookmarkable URL:

| URL Route | Primary Persona | Purpose & Capabilities |
| :--- | :--- | :--- |
| **`/sequencer`** | Device Developer / Test Lab Operator | **Sequencer Execution & Testbed Workspace**: Execute UDMI compliance sequences, inspect artifacts (`RESULT.log`, `sequence.md`, `sequence.png`), filter tests by minimum stage and result status, and manage the local test substrate via the integrated right-hand **Local Test Setup Drawer**. Supports direct one-click Mantis failure triage. |
| **`/devices`** (or `/devices/:deviceId`) | Developer / Curator | **Device Explorer**: Inspect device metadata, pointsets, gateway bindings, and raw telemetry trace payloads. |
| **`/assistant`** | Developer / Operator / Curator | **Mantis Shrimp AI Reasoning Workspace**: Conversational domain expert and automated failure triage. Automatically consumes failed test context from `/sequencer`, evaluates the 9-hypothesis diagnostic matrix, and suggests remediations. Includes `← Back to Sequencer` breadcrumbs. Supports deep links such as `/assistant?q=What+is+configAcked+in+state`. |
| **`/diagnostics`** | Operator / Developer | **System Telemetry & Diagnostics**: Real-time diagnostic ring buffer, structured log stream, and system health status. |
| **`/compliance`** | Ecosystem Curator / Operator | **Compliance Matrix Dashboard**: Device x Test grid, flakiness index, pass/fail KPIs, and certification status. |
| **`/catalog`** | Ecosystem Curator | **Certified Device Catalog**: Curated menu of approved, certified IoT devices for production installations. |

#### Dual Interaction Modalities for Mantis
1. **Dedicated Workspace (`/assistant`)**: Full-page interactive workspace for deep architectural queries, specification review, and open-ended exploration.
2. **Direct Failure Triage Action**: One-click `[🔍 Diagnose with Mantis]` action directly on failed test rows in `/sequencer` and within the Artifact Viewer modal, automatically passing failure context (`site_model`, `device_id`, `test_id`) into Mantis and navigating to `/assistant` with a return breadcrumb.
3. **Global Contextual Drawer (`Cmd+K` / `Ctrl+K`)**: Persistent slide-out drawer accessible from any route, inheriting the active view's context.

---

### 3.2. Local Test Setup Drawer (Sequencer Screen Integration)

To eliminate the need for test operators to switch between terminal windows and the browser, Workbench integrates a persistent, collapsible **Local Test Setup Drawer** directly docked to the right side of the `/sequencer` tab.

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Sequencer Workspace (/sequencer)                                       │ [Local Setup Drawer]     │
│ ┌────────────────────────────────────────────────────────────────────┐ │ ┌───────────────────────┐│
│ │ Run Configuration (Site Model, Device, Target Spec)                │ │ │ [Start] [Stop] [Restart││
│ ├────────────────────────────────────────────────────────────────────┤ │ ├───────────────────────┤│
│ │ Filter Bar [Min Stage: STABLE ▼] [All] [None] [Pass] [Skip] [Fail] │ │ │ Topology Graph        ││
│ ├────────────────────────────────────────────────────────────────────┤ │ │  [DUT / Pubber]       ││
│ │ Sequences Table                                                    │ │ │        │ (MQTT:18833) ││
│ │ ┌───────────────────────┬────────┬──────────┬────────────────────┐ │ │ │        ▼              ││
│ │ │ Test Name             │ Stage  │ Status   │ Actions            │ │ │ │  [Mosquitto Broker]   ││
│ │ ├───────────────────────┼────────┼──────────┼────────────────────┤ │ │ │        │ (Reflective) ││
│ │ │ pointset_publish      │ STABLE │ PASSED   │ [View Artifacts]   │ │ │ │        ▼              ││
│ │ │ system_last_start     │ STABLE │ FAILED   │ [🔍 Mantis Triage] │ │ │ │  [Local UDMIS Pod]    ││
│ │ └───────────────────────┴────────┴──────────┴────────────────────┘ │ │ │        │ (KV State)   ││
│ ├────────────────────────────────────────────────────────────────────┤ │ │        ▼              ││
│ │ Live Execution Logs Console (SSE stream)                           │ │ │  [etcd State Store]   ││
│ └────────────────────────────────────────────────────────────────────┘ │ └───────────────────────┘│
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### 3.2.1. Drawer Affordance & Behavior
- **Trigger**: An action button in the Sequencer header/toolbar (`[🖥️ Local Setup]`) with an integrated live health status dot (🟢 All UP, 🟡 Initializing/Partial, ⚪ Stopped, 🔴 Error). Also toggled via shortcut `Cmd+Shift+L` / `Ctrl+Shift+L`.
- **Slide-out Animation & Layout**: Smooth CSS transform transition from the right edge, overlaying or resizing the Sequencer table without unmounting any DOM components or interrupting active test runs.
- **State Persistence**: Drawer state (`open` / `closed`) is persisted in `localStorage` (`udmi_testbed_drawer_open`).

#### 3.2.2. Interactive Topology Graph
The drawer hosts an interactive SVG/HTML canvas that visually displays the active local infrastructure components and their data connections:
- **Topology Nodes**:
  1. **Device Under Test (DUT)**:
     - Represents the active device selected in the Sequencer (`activeDevice`).
     - **Mode Switch**: Toggle button between **Simulated Pubber** (runs local `bin/pubber`) and **Physical Device** (hardware connected over network/Wi-Fi).
     - Live indicator: `UP` (running/connected), `DOWN` (stopped), `TESTING` (active test in progress).
  2. **Local MQTT Broker (Mosquitto)**:
     - Runs on unprivileged user-space port `18833` (`//mqtt/localhost:18833`).
     - Live indicator: `UP` (TCP socket 18833 open and accepting connections), `DOWN` (port closed).
  3. **Local UDMIS (UDMI Service Pod)**:
     - Local message processing pipeline executing reflective mapping, state synchronization, and schema validation.
     - Live indicator: `UP` (PID active + `var/pod_ready.txt` sentinel verified), `INITIALIZING` (PID active, awaiting pod ready), `DOWN` (inactive).
  4. **etcd State Store**:
     - Local key-value store maintaining dynamic device state and site registry metadata on unprivileged port (`2379` / `35951`).
     - Live indicator: `UP` (socket open/responding), `DOWN` (stopped).
- **Logical Flow Edges**:
  - `DUT -> MQTT Broker`: MQTT Telemetry (`events/*`) and State (`state`) via QoS 1.
  - `MQTT Broker -> UDMIS`: Reflective ingest and event routing.
  - `UDMIS -> etcd`: Key-value state persistence and metadata lookups.
  - `UDMIS -> MQTT Broker -> DUT`: Target configuration writeback (`config`) and system commands.

#### 3.2.3. Component Health Probes & Status State Machine
Components transition through strict, deterministic states:
- `UP`: Process running and socket/readiness sentinel confirmed.
- `INITIALIZING`: Process launched; awaiting socket binding or sentinel creation (maximum 90s startup timeout per project standard).
- `DOWN`: Component stopped, process terminated, port released.
- `ERROR`: Component crashed, port collision, or health probe timeout.

**Probe Implementations**:
- **Mosquitto**: Non-blocking TCP socket check against `localhost:18833`.
- **UDMIS**: Detection of active UDMIS process and existence of `var/pod_ready.txt` sentinel.
- **etcd**: Non-blocking TCP socket check against etcd client port.
- **Pubber**: Process check (`pgrep -f pubber`) and verification that the PID matches the active device ID.

#### 3.2.4. Lifecycle Control Actions
- **Start Local Setup**:
  - Invokes `POST /api/testbed/start` with payload `{"site_model": "<active_site_model>", "project_spec": "//mqtt/localhost:18833"}`.
  - Executes `bin/udmi start` using unprivileged ports.
  - Automatically updates the Sequencer's `projectSpec` input to `//mqtt/localhost:18833`.
  - Sets component statuses to `INITIALIZING`, streaming startup progress until `UUFI Service is READY`.
- **Stop Local Setup**:
  - Invokes `POST /api/testbed/stop`.
  - Executes `bin/udmi stop`, terminating tmux sessions, killing background processes, and updating node states to `DOWN`.
- **Restart (Clean Slate)**:
  - Invokes `POST /api/testbed/restart`.
  - Executes `bin/udmi restart`, purging stale ephemeral state (`var/`), clearing cached keys, and launching clean services.
- **Pubber Emulator Launcher / Toggle**:
  - When in Pubber mode, enables starting and stopping simulated device instances:
    - Launch: `POST /api/testbed/pubber/start` (`bin/pubber <site_model> //mqtt/localhost:18833 <device_id> <serial_no>`).
    - Terminate: `POST /api/testbed/pubber/stop`.
- **Setup Logs Viewer**:
  - Embedded collapsible log console within the drawer allowing operators to inspect startup logs, Mosquitto traffic, UDMIS pipeline logs, and Pubber output.

---

## 4. Contract 1: MCP Tool & Resource Contract (Deterministic Operations)

* **Protocol**: Model Context Protocol (MCP) JSON-RPC 2.0 over HTTP/SSE or stdio.
* **Endpoints**:
  - `GET /sse`: Establishes the MCP event stream.
  - `POST /message` or `POST /rpc`: Dispatches JSON-RPC requests.

### 4.1. Supported JSON-RPC Methods
- `initialize`: Client handshake, protocol negotiation.
- `ping`: Keep-alive health check.
- `tools/list`: Returns all registered tools and their JSON schemas.
- `tools/call`: Executes a tool deterministically and returns structured content.
- `resources/list` & `resources/read`: Inspects URI-based resources.

### 4.2. Tool Registry Mapping to Workbench Features

#### A. Environment & Test Cadre Lifecycle (Test Lab Operator)
* **`ensure_test_setup`**:
  * **Args**: `{"test_id": "lab_run_1", "site_model": "sites/udmi_site_model", "clean": true, "timeout_seconds": 150}`
  * **Swappable Component Flags**: `--exclude` (`-x udmis influxdb`), `--added` (`-a validator spotter`), `--dut` (`AHU-1`).
  * **Output**: `{"status": "READY", "project_spec": "//mqtt/localhost:20000", "ports": {"mqtt": 20000, "etcd": 20001, "influx": 20002, "postgres": 20003}, "windows": ["main", "dut", "sequencer", "butler", "validator"]}`
* **`terminate_test_setup`**:
  * **Args**: `{"test_id": "lab_run_1", "clean_workspace": true}`
* **`list_test_setups`**:
  * **Args**: `{}`
  * **Output**: Active running sessions, connection URLs, port blocks, and active windows.
* **`list_test_windows`**:
  * **Args**: `{"test_id": "lab_run_1"}`

#### B. Sequencer Execution (Operator & Developer)
* **`run_sequencer_test`**:
  * **Args**: `{"test_name": "pointset_publish", "device_id": "AHU-1", "target_spec": "//mqtt/localhost:20000", "site_model": "sites/udmi_site_model"}`
  * **Output**: `{"status": "LAUNCHED", "session_id": "udmi_lab_run_1", "window": "sequencer", "command": "bin/sequencer ..."}`
* **`inspect_sequencer_test`**:
  * **Args**: `{"test_name": "pointset_publish"}`
  * **Output**: Extracts `@Feature` bucket, stage (`ALPHA`, `BETA`, `STABLE`), timeout, javadoc, assertions, and exact Java source.

#### C. Site Model, Devices & Schemas (Developer & Curator)
* **`inspect_site_model`**:
  * **Args**: `{"site_model": "sites/udmi_site_model", "device_id": "AHU-1"}`
  * **Output**: Device metadata, points list, cloud IoT config, gateway bindings.
* **`patch_site_model`**:
  * **Args**: `{"site_model": "sites/udmi_site_model", "device_id": "AHU-1", "patch_data": {"points": {"temp_sensor": {"units": "degC"}}}, "dry_run": false}`
  * **Output**: Unified diff, backup file path (`.bak`), patch status.
* **`inspect_udmi_schema`**:
  * **Args**: `{"schema_name": "pointset", "resolve_refs": true}`
  * **Output**: JSON Schema definitions with resolved `$ref` pointers.

##### Custom Site Model Roots & Allow-Listing Contract
Site models may reside outside the UDMI root directory. To respect user security and privacy, custom directories require explicit user consent via the UI consent modal and are recorded in local storage and backend state:
* **`GET /api/site-roots`**: Returns list of approved root paths and discovered site models.
* **`POST /api/site-roots/register`**: Registers an allow-listed root path (`{"path": "/path/to/sites"}`).
* **`POST /api/site-roots/delete`**: Revokes an allow-listed root path.
* **Dual Site Model Directory Convention**:
  - **Standard Root**: `<site_dir>/cloud_iot_config.json` (e.g. `sites/udmi_site_model`).
  - **Subdirectory Convention**: `<site_dir>/udmi/cloud_iot_config.json` (e.g. `UK-LON-GLAB/udmi/cloud_iot_config.json`).
  - **Canonical Display Name**: When `<site_dir>/udmi/cloud_iot_config.json` is discovered, the UI and API display the parent directory (`UK-LON-GLAB`), rejecting the generic inner name `udmi`.

#### D. Visualizations (Developer & Curator)
* **`generate_topology_diagram`**:
  * **Args**: `{"site_model": "sites/udmi_site_model"}`
  * **Output**: DOT graph syntax and Mermaid diagram syntax.
* **`generate_sequence_diagram`**:
  * **Args**: `{"log_path": "out/devices/AHU-1/tests/pointset_publish/sequence.log"}`
  * **Output**: Transactional sequence flow in DOT and Mermaid.
* **`render_dot_to_svg`**:
  * **Args**: `{"dot_content": "digraph G { ... }"}`
  * **Output**: Rendered, browser-ready SVG string.

#### E. Local Testbed & Cadre REST Endpoints (Local Infrastructure & Lifecycle)
The local testbed substrate is managed deterministically via dedicated REST endpoints called by the **Local Test Setup Drawer**:
* **`POST /api/testbed/start`**:
  * **Request**: `{"site_model": "sites/udmi_site_model", "project_spec": "//mqtt/localhost:18833", "clean": false}`
  * **Behavior**: Runs `bin/udmi start` targeting unprivileged user-space ports (MQTT 18833, etcd, postgres, influx). Fails fast if port conflicts or invalid site model.
  * **Response**: `{"status": "INITIALIZING", "session_id": "udmi_barbican~default", "project_spec": "//mqtt/localhost:18833", "ports": {"mqtt": 18833, "etcd": 2379}}`
* **`POST /api/testbed/stop`**:
  * **Request**: `{}`
  * **Behavior**: Runs `bin/udmi stop`, terminating tmux sessions, killing background processes, and releasing allocated ports.
  * **Response**: `{"status": "STOPPED", "message": "All local pipeline services stopped"}`
* **`POST /api/testbed/restart`**:
  * **Request**: `{"site_model": "sites/udmi_site_model", "project_spec": "//mqtt/localhost:18833"}`
  * **Behavior**: Runs `bin/udmi restart` (stop, clean state in `var/`, start).
  * **Response**: `{"status": "INITIALIZING", "project_spec": "//mqtt/localhost:18833"}`
* **`GET /api/testbed/status`**:
  * **Behavior**: Executes non-blocking diagnostic probes against all local components.
  * **Response**:
    ```json
    {
      "overall": "UP",
      "project_spec": "//mqtt/localhost:18833",
      "components": {
        "mqtt_broker": {"status": "UP", "port": 18833, "pid": 1311904, "probe": "tcp://localhost:18833"},
        "udmis": {"status": "UP", "pid": 1311658, "sentinel": "var/pod_ready.txt", "probe": "pod_ready"},
        "etcd": {"status": "UP", "port": 2379, "pid": 1311605, "probe": "tcp://localhost:2379"},
        "pubber": {"status": "DOWN", "pid": null, "device_id": null}
      }
    }
    ```
* **`POST /api/testbed/pubber/start`**:
  * **Request**: `{"site_model": "sites/udmi_site_model", "project_spec": "//mqtt/localhost:18833", "device_id": "AHU-1", "serial_no": "1234"}`
  * **Behavior**: Runs `bin/pubber` in background for the specified device.
  * **Response**: `{"status": "RUNNING", "device_id": "AHU-1", "pid": 1312500}`
* **`POST /api/testbed/pubber/stop`**:
  * **Request**: `{"device_id": "AHU-1"}`
  * **Behavior**: Kills the running pubber process for the specified device.
  * **Response**: `{"status": "STOPPED", "device_id": "AHU-1"}`
* **`GET /api/testbed/logs`**:
  * **Query Params**: `component=mosquitto|udmis|etcd|pubber&tail=200`
  * **Response**: `{"component": "mosquitto", "logs": "..."}`

---

## 5. Contract 2: Streaming AI Agent Contract (Mantis Cognitive Loop)

* **Protocol**: Server-Sent Events (SSE) via `POST /api/mantis/chat` or `POST /api/mantis/triage`.
* **Purpose**: Orchestrating multi-turn, multi-step ReAct investigations (`Actor -> Critic -> Arbitrator`) with real-time reasoning, tool audit visibility, and hypothesis evaluation.

### 5.1. Dual Agent Execution Modes

Mantis operates in two distinct execution modes based on the request context:

#### Mode A: Targeted Failure Triage Mode
* **Triggered by**:
  - Direct Sequencer Action: Clicking `[🔍 Diagnose with Mantis]` on any failed test row in `/sequencer` or within the Artifact Viewer modal. Automatically packages `{ site_model, device_id, test_id }`, switches to `/assistant`, and executes automated diagnosis.
  - Interactive selection from the failed test dropdown selector on `/assistant`.
  - Direct route access: `/triage/:sessionId` or clicking a failed test in `/compliance`.
* **Behavior**: Focuses on root-cause diagnosis. Extracts test timelines (`get_test_timeline`), validates schemas (`inspect_udmi_schema`), cross-references logs (`detect_log_anomalies`), runs the tripartite audit (`Actor -> Critic -> Arbitrator`), and produces a ranked hypothesis matrix.
* **Return Navigation**: When launched from Sequencer, the Assistant renders a top breadcrumb action `← Back to Sequencer` allowing operators to instantly return to their running test suite without losing log state or test progress.

#### Mode B: General Exploration & Specification Mode
* **Triggered by**: `/assistant`, the global `Cmd+K` drawer with general queries, or queries without an active test failure (e.g. *"What is the state field configAcked and how does it relate to config synchronization?"*).
* **Behavior**: Operates as an interactive domain expert. Automatically identifies relevant schemas (`inspect_udmi_schema`), locates authoritative specifications (`locate_udmi_doc`), searches codebase implementations (`search_codebase`), checks Java sequencer validation logic (`inspect_sequencer_test`), and produces grounded explanations and code snippets.

### 5.2. SSE Stream Protocol & Wire Schema

#### Example 1: Targeted Failure Triage Request
```http
POST /api/mantis/chat HTTP/1.1
Content-Type: application/json
Accept: text/event-stream

{
  "session_id": "sess-developer-ahu1",
  "message": "Why did pointset_publish fail for AHU-1?",
  "context": {
    "site_model": "sites/udmi_site_model",
    "device_id": "AHU-1",
    "test_id": "pointset_publish",
    "project_spec": "//mqtt/localhost:18833",
    "baseline_run": "out/mantis/baseline_pass"
  },
  "provider_override": {
    "provider": "vertex",
    "gcp_project": "bos-platform-dev",
    "gcp_location": "global"
  }
}
```

#### Example 2: General Exploration Request (`/assistant`)
```http
POST /api/mantis/chat HTTP/1.1
Content-Type: application/json
Accept: text/event-stream

{
  "session_id": "sess-assistant-general",
  "message": "What is the state field configAcked and how does it relate to config synchronization?",
  "context": {
    "site_model": "sites/udmi_site_model"
  }
}
```

### 5.3. Canonical Event Wire Schema

```
event: phase
data: {"phase": "ACTOR"}

event: thought
data: {"text": "Inspecting sequence execution logs and schema validation errors for AHU-1..."}

event: tool_call
data: {"call_id": "call-1", "tool": "get_test_timeline", "args": {"test_id": "pointset_publish", "device_id": "AHU-1"}, "timestamp": "2026-09-15T15:00:00Z"}

event: tool_result
data: {"call_id": "call-1", "tool": "get_test_timeline", "summary": "Cutoff threshold violated at step 4", "output": {"transactions": ["RC:101"], "stale_state_detected": true}}

event: token
data: {"text": "The test failed because the device's state update lagged behind the cutoff threshold."}

event: phase
data: {"phase": "CRITIC"}

event: thought
data: {"text": "Auditing Actor hypothesis: verifying whether state was actually lagging or if the local broker dropped the packet."}

event: phase
data: {"phase": "ARBITRATOR"}

event: hypothesis_matrix
data: {
  "hypotheses": [
    {
      "hypothesis": "State update message arrived after cutoff timestamp",
      "verdict": "PRIMARY",
      "rationale": "Sequence log line 142 confirms timestamp delta +4.2s exceeds 2.0s limit",
      "evidence_tier": "LOCAL_FILE"
    },
    {
      "hypothesis": "Broker dropped QoS 1 state message",
      "verdict": "REFUTED",
      "rationale": "Mosquitto log confirms PUBACK received with RC:0",
      "evidence_tier": "LOCAL_FILE"
    }
  ]
}

event: diagram
data: {"type": "sequence", "format": "svg", "content": "<svg ...>...</svg>"}

event: done
data: {
  "session_id": "sess-developer-ahu1",
  "full_text": "...",
  "metrics": {
    "total_steps": 14,
    "total_duration_sec": 8.4,
    "api_calls_count": 3,
    "tool_calls": {"get_test_timeline": 1, "inspect_udmi_schema": 1}
  }
}
```

### 5.3. Session Control Endpoints
* **`POST /api/mantis/session/stop`**: Cancels active inference or tool execution: `{"session_id": "string"}`.
* **`POST /api/mantis/session/clear`**: Resets conversation turns while preserving environment state: `{"session_id": "string"}`.
* **`GET /api/mantis/session/status?session_id=...`**: Returns active context, tokens consumed, loaded skills, and active test stacks.

### 5.4. Canonical Slash Commands (In Chat Prompt)
- `/status`: Returns active system status, loaded skills, and running test environments.
- `/logs <window>`: Fetches recent terminal buffer from a named tmux window.
- `/clear`: Clears conversation history while preserving environment state.
- `/export [filename]`: Generates a downloadable Markdown diagnostic report.
- `/help`: Displays command syntax.

### 5.5. Layer 0 Canonical Pydantic Models (`mantis/models.py`)

All data structures in Mantis are strictly defined with Pydantic:

```python
class ClaimStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    UNVERIFIED_ASSUMPTION = "UNVERIFIED ASSUMPTION"

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    timestamp: str  # ISO-8601
    tool_name: Optional[str] = None
    tool_call_id: Optional[str] = None

class ExecutionMetrics(BaseModel):
    total_steps: int = 0
    total_duration_sec: float = 0.0
    api_calls_count: int = 0
    prompt_tokens: int = 0
    candidates_tokens: int = 0
    total_tokens: int = 0
    tool_calls: Dict[str, int] = Field(default_factory=dict)
    retry_count: int = 0
    tripartite_degraded: bool = False
    tripartite_status: str = "SUCCESS"

class SessionContext(BaseModel):
    active_site_model: str = "sites/udmi_site_model"
    active_session_id: Optional[str] = None
    active_device_id: Optional[str] = None
    active_test_id: Optional[str] = None
    history: List[ChatMessage] = Field(default_factory=list)
    metrics: Optional[ExecutionMetrics] = None

class VerificationClaim(BaseModel):
    claim: str
    status: ClaimStatus
    evidence: str

class HypothesisEvaluation(BaseModel):
    status: ClaimStatus
    evidence: str

class DiagnosticResult(BaseModel):
    status: str = "SUCCESS"
    test_id: str
    device_id: str
    site_model: str
    root_cause: str
    evidence: List[str]
    fix: List[str]
    verification_matrix: List[VerificationClaim]
    competing_hypotheses: Dict[str, HypothesisEvaluation]
    timeline: Optional[Dict[str, Any]] = None
    report: str
    error: Optional[str] = None
```

### 5.6. Native Python SDK & Streaming Adapter

For backend servers implemented in Python (e.g. FastAPI / Starlette), Mantis can be called directly without subprocess overhead:

```python
import asyncio
import json
import threading
from mantis.agent import MantisAgent
from mantis.context import ContextManager
from mantis.models import SessionContext

agent = MantisAgent()

async def stream_mantis_response(user_query: str, context: SessionContext):
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    def stream_callback(chunk: str):
        loop.call_soon_threadsafe(queue.put_nowait, {"type": "token", "text": chunk})

    def run_sync():
        try:
            full_result = agent.run_tripartite(
                user_query,
                context=context,
                stream_callback=stream_callback
            )
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "done", "full_text": full_result})
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(e)})

    threading.Thread(target=run_sync, daemon=True).start()

    while True:
        event = await queue.get()
        yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
        if event['type'] in ("done", "error"):
            break
```

---

## 6. Contract 3: Real-Time Log Streaming Contract (Live Monitoring)

* **Protocol**: Server-Sent Events (SSE) or WebSocket.
* **Endpoint**: `GET /api/logs/stream?session_id=<session>&window=<window>&tail=<lines>`
* **Purpose**: Provides live console monitoring for Test Lab Operators and Developers during active runs.

### 6.1. Log Stream Wire Format
```http
GET /api/logs/stream?session_id=udmi_lab_run_1&window=sequencer HTTP/1.1
Accept: text/event-stream

event: log_chunk
data: {"window": "sequencer", "timestamp": "2026-09-15T15:02:10.123Z", "text": "Starting sequence pointset_publish on AHU-1...\n"}

event: log_chunk
data: {"window": "sequencer", "timestamp": "2026-09-15T15:02:12.456Z", "text": "Waiting for config update synchronization...\n"}

event: status_change
data: {"window": "sequencer", "state": "COMPLETED", "exit_code": 0}
```

---

## 7. Contract 4: UI State & Workspace Contract (Client-Side State Store)

* **Implementation**: Central reactive store in the frontend SPA (e.g., Zustand, Pinia, Nanostores, or native `EventTarget`).
* **Purpose**: Single source of truth for the browser application, providing reactive state updates across all views.

### 7.1. TypeScript State Store Schema
```typescript
export interface ComponentHealth {
  status: 'UP' | 'INITIALIZING' | 'DOWN' | 'ERROR';
  pid?: number | null;
  port?: number | null;
  probe?: string;
  sentinel?: string;
  error?: string;
}

export interface WorkspaceState {
  // Active Project & Target Hierarchy
  siteModel: string;                  // e.g. 'sites/udmi_site_model'
  activeDevice: string;               // e.g. 'AHU-1'
  activeTest: string;                 // e.g. 'pointset_publish'
  projectSpec: string;                // e.g. '//mqtt/localhost:18833' or '//gbos/...'
  minStage: 'ALPHA' | 'BETA' | 'PREVIEW' | 'STABLE'; // Minimum stage filter

  // Custom Site Roots & Allow-listing
  customSiteRoots: string[];          // Allow-listed external site root paths

  // Local Testbed & Infrastructure Drawer State
  testbedDrawerOpen: boolean;         // Right-side drawer open/closed state
  testbedStatus: {
    overall: 'UP' | 'INITIALIZING' | 'DOWN' | 'ERROR';
    projectSpec: string;
    components: {
      mqtt_broker: ComponentHealth;
      udmis: ComponentHealth;
      etcd: ComponentHealth;
      pubber: ComponentHealth & { deviceId?: string | null };
    };
  };

  // Test Cadre & Process Execution State
  setupMode: 'LOCAL' | 'CLOUD' | 'ATN_HYBRID';
  activeSessionId: string | null;     // e.g. 'udmi_lab_run_1'
  activeWindows: string[];            // ['main', 'dut', 'sequencer', 'butler', 'validator']
  portAllocations: {
    mqtt: number;
    etcd: number;
    influx: number;
    postgres: number;
  } | null;

  // Swappable Components Configuration
  swappableServices: {
    udmis: boolean;
    influxdb: boolean;
    postgres: boolean;
    validator: boolean;
    atn: boolean;                     // Ancillary Test Node writeback companion
  };

  // AI Provider & Settings
  aiConfig: {
    provider: 'vertex' | 'studio' | 'offline';
    gcpProject: string;
    gcpLocation: string;
    apiKey?: string;
  };

  // Compliance & KPI Cache
  complianceScores: {
    totalTests: number;
    passCount: number;
    failCount: number;
    flakinessIndex: number;
    deviceScores: Record<string, number>; // deviceId -> percentage
  };
}
```

### 7.2. SPA View Preservation & Non-Destructive DOM Caching
To ensure that long-running test suites, streaming SSE consoles, and interactive triage workflows are never interrupted or lost during user navigation:
1. **Persistent View-Pane Containers**: Each route view (`/sequencer`, `/devices`, `/assistant`, `/diagnostics`) is instantiated once and mounted inside its own `.view-pane` container.
2. **Non-Destructive Navigation**: Route switching toggles the `active` class / visibility (`display: none` vs `display: flex/block`) of `.view-pane` elements instead of destroying and recreating DOM nodes.
3. **Execution Continuity**:
   - Background SSE streams (such as `bin/sequencer` live execution logs and Mantis reasoning tokens) continue streaming without reset when switching between views.
   - Test results tables, filter states, and scroll positions in the Sequencer view are preserved when a user navigates to `/assistant` to diagnose a failure and returns via `← Back to Sequencer`.
   - Discovery loaders retain cached `testStatus` results across device selections rather than wiping out previous run outputs.

---

## 8. Contract 5: Compliance & Reporting Contract (Ecosystem Curation)

* **Purpose**: Producing standardized, exportable test result packages and compliance matrices for Ecosystem Curators to certify and catalog approved IoT devices.

### 8.1. Compliance Matrix Data Schema (`GET /api/compliance/matrix`)
```json
{
  "site_model": "sites/udmi_site_model",
  "generated_at": "2026-09-15T15:00:00Z",
  "summary": {
    "total_devices": 12,
    "certified_devices": 10,
    "compliance_rate_pct": 83.3,
    "average_flakiness_index": 0.02
  },
  "devices": [
    {
      "device_id": "AHU-1",
      "model": "Siemens Desigo PXC",
      "firmware_version": "4.2.1",
      "status": "CERTIFIED",
      "score_pct": 100.0,
      "tests": {
        "pointset_publish": {"status": "PASSED", "duration_sec": 4.2, "stage": "STABLE"},
        "system_last_start": {"status": "PASSED", "duration_sec": 2.1, "stage": "STABLE"},
        "writeback_validation": {"status": "PASSED", "duration_sec": 6.8, "stage": "BETA", "atn_verified": true}
      }
    },
    {
      "device_id": "EM-11",
      "model": "Schneider PowerLogic",
      "firmware_version": "1.0.8",
      "status": "NON_COMPLIANT",
      "score_pct": 66.7,
      "tests": {
        "pointset_publish": {"status": "FAILED", "stage": "STABLE", "root_cause": "Clock drift / sub-device caching issue"},
        "system_last_start": {"status": "PASSED", "stage": "STABLE"}
      }
    }
  ]
}
```

### 8.2. Exportable Device Certification Package
When a curator approves a device, Workbench exports a standardized zip bundle:
- `device_spec.json`: Target device metadata, points, and schemas.
- `compliance_report.md`: Human-readable markdown audit report.
- `certification_token.json`: Cryptographic hash of test logs, site model, and test outputs.
- `traces/`: Raw MQTT traces (`events_pointset.json`, `state.json`, `config.json`).
- `diagrams/`: Graphviz SVG topology and Mermaid sequence diagrams.

---

## 9. Frontend UI Component Architecture Guidelines

The Workbench SPA layout is composed of the following key UX components:

1. **Diagnostic Drawer & Conversational Feed**:
   - Renders streaming Markdown (`token` events).
   - Collapsible **"Thinking / Internal Audit"** accordion displaying `thought` and `phase` transitions (`Actor -> Critic -> Arbitrator`).
   - Dynamic **Tool Call Badges**: Displays tool name, input arguments, and output preview with execution time.
2. **Hypothesis Audit Matrix**:
   - Visual comparison table showing competing hypotheses.
   - Status chips:
     - `PRIMARY`: Solid Red / Amber (The active failure cause).
     - `CONTRIBUTING`: Yellow / Amber (Aggravating or secondary factor).
     - `REFUTED`: Neutral Gray / Strike-through (Disproven by log evidence).
     - `UNRESOLVED`: Dashed Outline / Blue (Insufficient log evidence).
   - Evidence badges displaying the source tier (`LOCAL_FILE`, `CLOUD`, or `NONE: source inference only`).
3. **Diagrams Canvas**:
   - Interactive zoomable/pannable SVG viewer for Graphviz architecture topologies.
   - Mermaid.js sequence diagram viewer for protocol transaction flows (`sequenceDiagram`).
4. **Local Test Setup Drawer & Topology Canvas**:
   - Collapsible slide-out drawer on the right side of `/sequencer`.
   - SVG/HTML canvas rendering active component nodes (`DUT / Pubber`, `Mosquitto Broker`, `Local UDMIS Pod`, `etcd State Store`) and connection flow edges.
   - Live health indicator chips on each node (`UP`, `INITIALIZING`, `DOWN`, `ERROR`).
   - Real-time lifecycle actions: `[Start Local Setup]`, `[Stop]`, `[Restart]`, `[Pubber Launcher]`, `[View Logs]`.
5. **Sequencer Filter Toolbar**:
   - Unified filter bar placed directly above the sequences table.
   - Minimum Stage filter dropdown (`ALPHA`, `BETA`, `PREVIEW`, `STABLE`) directly adjacent to selection buttons (`Select All`, `None`), status toggles (`Passed`, `Skipped`, `Failed`), and search input.
   - Single canonical filter surface eliminating duplicate sidebar selectors.
6. **Site Roots Consent Modal**:
   - Manages user authorization for custom site model directories located outside the UDMI root.
   - Supports directory registration, listing, and revocation with persistent consent storage.
   - Handles standard root (`<site_dir>/cloud_iot_config.json`) and subdirectory layouts (`<site_dir>/udmi/cloud_iot_config.json`).
7. **Artifact Viewer Modal**:
   - Interactive preview of test artifacts: `RESULT.log`, `sequence.md`, `sequence.png`, JSON state/config diffs.
   - Includes direct `[🔍 Diagnose with Mantis]` action for instant triage without leaving the artifact view.
8. **Settings Modal**:
   - Provider toggle: **Google Cloud Vertex AI** (ADC, Project, Region) vs **Google AI Studio** (`GEMINI_API_KEY`) vs **Offline Deterministic**.

