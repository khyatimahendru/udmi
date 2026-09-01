# MANTIS Technical Specification

Mantis provides an autonomous diagnostic agent and management control plane for the Universal Device Management Interface (UDMI) ecosystem.

By unifying environmental provisioning, test execution, schema validation, and root-cause analysis into an agentic system, Mantis enables operators, test engineers, hardware vendors (OEMs), master systems integrators (MSIs), and automated developer tooling to interact directly with UDMI infrastructure through conversational and programmatic interfaces.

## Background & Context

UDMI defines schema-driven standards for managing operational technology (OT) physical devices in smart buildings. Running, testing, and debugging UDMI environments involves multiple reflectively coupled components:

* **Pubber**: Emulated IoT device client simulating pointset telemetry, device state, and configuration transitions.
* **Mosquitto MQTT**: Message transport routing packets across device sub-blocks (`events/*`, `state`, `config`).
* **UDMIS**: Core backend processor executing data translation, state sharding (`StateProcessor`), and configuration transactions (`ReflectProcessor`).
* **Butler**: Message router and database bridge synchronizing telemetry into InfluxDB and state records into PostgreSQL.
* **Validator & Sequencer**: Telemetry validation daemon and automated end-to-end integration test runner.

Triaging failures in this distributed ecosystem requires deep protocol knowledge:
1. **Timestamp Cutoff Races**: Test sequencers establish strict timestamp cutoff thresholds. Emulated or physical devices publishing cached state updates lagging by seconds are rejected as stale.
2. **Serialization & Schema Mismatches**: Minor JSON syntax errors in `metadata.json` fail the Java Jackson parser, causing the sequencer to fall back to state synchronization timeouts.
3. **Telemetry Cadence Discrepancies**: Devices polling sensors on 300-second intervals cause tests with 120-second wait conditions to time out.
4. **Gateway & Proxy Topologies**: Sub-devices behind field gateways (BACnet MSTP, Modbus RTU) introduce multi-hop routing failures and bus contention.

Mantis automates the isolation, reproduction, and remediation of these operational failures without relying on generic, abstract harness layers or fragmented command-line subcommands.

## Universal Interface Specification

Mantis follows a single universal execution paradigm:

* **Interactive Diagnostic Session**: `bin/mantis` (Launches multi-turn conversational console).
* **Headless Universal Execution**: `bin/mantis "<instruction>"` (Executes any instruction, query, test, or triage task autonomously and exits).
* **Model Context Protocol Server**: `bin/mantis --mcp` (Exposes stdio JSON-RPC 2.0 interface for external AI assistants).

## Implementation Specification

* Implemented in Python 3.11+ using the official Google GenAI SDK and Vertex AI client libraries.
* Process isolation and background daemon orchestration are managed through native `tmux` session workspaces (`mcp/session_manager.py`).
* Real-time telemetry and state database inspection is performed directly against runtime InfluxDB and PostgreSQL instances.
* Cognitive verification uses a built-in adversarial self-critique loop that audits claims, checks timestamp intervals, and stress-tests competing hypotheses before emitting reports.
* MCP integration provides standard tool schemas for external agents (Gemini CLI, Claude Code, Cursor, Windsurf) and local infrastructure control.
* Skills extensibility allows instant domain and protocol expansion through simple markdown files (`SKILL.md`).
* Self-Bootstrapping Runtime: `bin/mantis` automatically verifies and sets up the Python virtual environment (`venv`), dependencies (`bin/setup_base`), and system prerequisites on first launch before executing.

# Scope of Capabilities

Mantis provides seven core capability suites to operators and external agents.

## 1. Domain Intelligence & Specification Grounding

* **Authoritative Schema Inspection**: Direct querying, diffing, and validation across all schemas under `schema/` (`pointset.json`, `state_system.json`, `config_pointset.json`, `discovery.json`, etc.).
* **Site Model & Metadata Navigation**: Verification of `cloud_iot_config.json`, device `metadata.json`, gateway routing definitions, and telemetry point dictionaries.
* **Architecture Q&A**: Domain grounding in UDMI specification standards, envelope structures, and component interaction lifecycles.

## 2. Infrastructure & Environment Provisioning

* **Isolated Local Stack Deployment**: Automated provisioning of Mosquitto, UDMIS, Butler, InfluxDB, PostgreSQL, and Pubber DUTs in dedicated tmux workspaces.
* **Deterministic Port Allocation**: Automatic assignment of non-conflicting unprivileged port blocks per session ID ($\ge 20000$).
* **Dynamic Service Modifiers**: Selective inclusion (`++validator`) or exclusion (`!influxdb`) of stack components.
* **Session Persistence & Re-Attachment**: Automatic discovery and re-attachment to active tmux environments across terminal launches.

## 3. Gateway & Proxy Topology Management

* **Multi-Hop Topology Slicing**: Distinguishing between gateway connection drops (MQTT broker $\leftrightarrow$ Gateway) and proxy bus timeouts (Gateway $\leftrightarrow$ RS-485 Sub-device).
* **Discovery & Mapping Lifecycle**: Inspecting network discovery events (`discovery_events`), addressing conflicts, and automated candidate device enrollment.

## 4. Automated Sequencer Test Execution

* **Targeted Sequence Triggering**: Direct execution of sequencer test routines defined in `validator/.../sequences/` against active local or cloud endpoints.
* **Parameterized Sweeps**: Automated testing of multi-device fleets and protocol families (e.g. `scan_periodic_now_enumerate+bacnet`).
* **Stability Evaluation**: Multi-run iteration execution, statistical aggregation, and flake-rate computation across test run archives.

## 5. Deep Triage & Root Cause Analysis

* **Built-in Adversarial Critique**: Automated claim-by-claim verification of diagnostic theories against raw logs, timestamps, and schema definitions.
* **Behavioral Differential Sequence Analysis**: Protocol-level alignment of reference passing runs against failing runs to pinpoint exact state machine divergence.
* **Stale Cutoff & Serialization Detection**: Automated detection of sequencer timestamp cutoff threshold rejections and Jackson parser failures.

## 6. Automated Remediation & Safe Mutation

* **Safe Mutation Contracts**: All automated configuration or metadata modifications generate dry-run diffs and automatic `.bak` snapshots prior to application.
* **Metadata Auto-Patcher**: Programmatic correction of syntax errors, missing point definitions, or `testing: { nostate: true }` configurations in `metadata.json`.
* **Sequencer Assertion Fixer**: Identification of race conditions or outdated assertions in Java test files with targeted patch generation.

## 7. Golden Baseline & CI/CD Regression Prevention

* **Regression Verification**: Headless validation of test run outputs against golden expectation baselines (`etc/sequencer.out`, `etc/validator.out`).
* **Anti-Cheating Guard**: Verification that baseline diffs represent intentional, documented schema changes rather than test timing workarounds.

# High-Level Technical Architecture

```
+-----------------------------------------------------------------------------+
|                               MANTIS CORE                                   |
|                                                                             |
|  +-----------------------+  +----------------------+  +------------------+  |
|  | Universal CLI / REPL  |  |  ReAct Planner Core  |  | Built-in Critic  |  |
|  +-----------------------+  +----------------------+  +------------------+  |
|                             |                      |                        |
|                             v                      v                        |
|  +-----------------------------------------------------------------------+  |
|  |                             Tool Suite                                |  |
|  |  * environment (ensure_setup, terminate, get_logs)                    |  |
|  |  * execution (run_sequencer, test_sweep)                              |  |
|  |  * diagnostics (compare_sequences, extract_timeline)                  |  |
|  |  * schemas & site_models (inspect_schema, patch_metadata)             |  |
|  |  * telemetry_probing (query_db, inject_mqtt)                          |  |
|  +-----------------------------------------------------------------------+  |
|                             |                      |                        |
|                             v                      v                        |
|  +-----------------------------------------------------------------------+  |
|  |                     Session & Process Controller                      |  |
|  |  * Deterministic Port Allocator (MQTT, etcd, Influx, Postgres)        |  |
|  |  * Tmux Multi-Window Supervisor (main, dut, sequencer, butler)        |  |
|  |  * Semantic Window Log Streamer & Buffer Capturer                     |  |
|  +-----------------------------------------------------------------------+  |
+-----------------------------------------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------+
|                      UDMI System Under Test (Local / Cloud)                 |
|  Mosquitto MQTT | UDMIS Processor | Butler Bridge | InfluxDB | PostgreSQL   |
+-----------------------------------------------------------------------------+
```

## Model Routing & Performance Tiering

Mantis optimizes token usage, latency, and reasoning depth using a two-tier model routing architecture:

```
                      [User Query / Task]
                               │
                               ▼
                    [Intent Classification]
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
     [Flash Tier]                           [Pro Tier]
(gemini-2.5-flash-lite)                (gemini-2.0-pro / 3.1)
  * Entity extraction                    * Multi-stage root cause analysis
  * Log window slicing                   * Differential sequence alignment
  * Tool-output condensation             * Built-in adversarial critique loop
  * General schema lookups               * Complex code & metadata patching
```

### Provider Resolution & Environment Configuration
Mantis automatically resolves credentials in order of precedence:
1. **Google Cloud Vertex AI**: Activated when Application Default Credentials (`gcloud auth application-default login`) or `MANTIS_USE_VERTEXAI=true` are detected.
2. **Google AI Studio**: Activated when `GEMINI_API_KEY` is present.
3. **Deterministic Offline Mode**: When no AI API credentials are present, Mantis operates in deterministic mode (providing raw timelines, diffs, schema queries, and environment management without LLM synthesis).

## Session Management & Port Allocation

Local infrastructure instances are housed under `var/instances/udmi_<session_id>/`.

Port blocks are computed deterministically from the session ID string:

$$\text{BasePort} = 20000 + \left( \text{SHA256}(\text{SessionID}) \pmod{3500} \right) \times 10$$

* `BasePort + 0`: Mosquitto MQTT Transport (`//mqtt/localhost:<port>`)
* `BasePort + 1`: etcd Key-Value Storage
* `BasePort + 2`: InfluxDB Time-Series Telemetry Store
* `BasePort + 3`: PostgreSQL Relational Store
* `BasePort + 1001`: etcd Peer Coordination

## Built-In Cognitive Loop & Function-Calling Engine

Mantis implements a multi-step ReAct (*Reasoning + Acting*) cognitive execution loop:

1. **Tool Binding & Declaration**: The 14 domain tools from [`mantis/tools/registry.py`](file:///usr/local/google/home/heykhyati/Projects/udmi/mantis/tools/registry.py) are bound as native `google.genai.types.Tool` declarations and provided to the model.
2. **Iterative ReAct Execution**:
   $$\text{User Instruction} \rightarrow \text{LLM Thought} \rightarrow \text{Tool Invocation} \rightarrow \text{Observation} \rightarrow \text{Synthesis}$$
   The agent iterates up to `max_steps` (default: 10), capturing tool outputs and feeding them back as function responses until the model emits its final verified answer.
3. **Mandatory 3-Phase Diagnostic Cycle**:
   - **Phase 1: Evidence Harvesting**: Uses tools (`get_test_timeline`, `inspect_site_model`, `inspect_udmi_schema`) to gather timestamps, cutoff deltas, and transaction IDs (`RC:...`).
   - **Phase 2: Adversarial Self-Audit (Critic)**: Evaluates a Claim-by-Claim Verification Matrix (`CONFIRMED`, `REFUTED`, `UNVERIFIED ASSUMPTION`), testing and invalidating rival failure hypotheses.
   - **Phase 3: Verified Synthesis**: Emits the final report with Root Cause, Evidence, Fix suggestions, and optional Mermaid sequence diagrams.

## Model Context Protocol (MCP) Integration

All tool schemas and execution logic are centralized in [`mantis/tools/registry.py`](file:///usr/local/google/home/heykhyati/Projects/udmi/mantis/tools/registry.py) and consumed identically by the internal ReAct engine and the external MCP server ([`mcp/server.py`](file:///usr/local/google/home/heykhyati/Projects/udmi/mcp/server.py)). `bin/mantis --mcp` delegates directly to `mcp.server.main()`, exposing the complete 4-tier UDMI tool suite over stdio JSON-RPC 2.0.

## Testing & Verification Standards

In accordance with project engineering standards (`GEMINI.md`), Mantis implementation verification must satisfy two stages:

* **Stage 1: Unit & Static Integration Integrity (`bin/test_mantis`)**: Verifies argument parsing, session management, port calculation, schema inspection, differential alignment, and MCP serialization without external network access.
* **Stage 2: Functional Pipeline Integrity**: Validates local stack startup within 90 seconds, live sequencer triggering, and automatic reproduction of known failure signatures under negative verification.

* [**`mantis/COMMANDS.md`**](file:///usr/local/google/home/heykhyati/Projects/udmi/mantis/COMMANDS.md): Universal execution model, natural language routing, and canonical session commands.
* [**`mantis/DIAGNOSTICS.md`**](file:///usr/local/google/home/heykhyati/Projects/udmi/mantis/DIAGNOSTICS.md): Built-in adversarial critique engine, differential triage, gateway heuristics, and diagramming contracts.
* [**`mantis/MCP.md`**](file:///usr/local/google/home/heykhyati/Projects/udmi/mantis/MCP.md): Model Context Protocol (MCP) composable 4-tier tool architecture and JSON-RPC 2.0 schemas.
* [**`mantis/SKILLS.md`**](file:///usr/local/google/home/heykhyati/Projects/udmi/mantis/SKILLS.md): Skill extensibility subsystem and markdown knowledge base specification.
* [**`mantis/PLAN.md`**](file:///usr/local/google/home/heykhyati/Projects/udmi/mantis/PLAN.md): Detailed architectural implementation plan, phase roadmap, and regression prevention strategy.
