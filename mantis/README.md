# Mantis: Autonomous UDMI Agent & Diagnostic Management Control Plane

Mantis is an autonomous, production-grade AI agent and management control plane for the **Universal Device Management Interface (UDMI)**, modeled after Jetski. Mantis assists developers, field engineers, and system integrators with UDMI exploration, schema validation, test execution, failure root-cause analysis, and architectural visualization.

---

## 1. Architectural Principles

1. **Codebase as Single Source of Truth (SSoT)**:
   Mantis does not hardcode schemas, state transition tables, or device failure rules. The UDMI repository (`schema/`, `docs/specs/`, `docs/messages/`, and Java sequencer classes) is always inspected dynamically to prevent documentation and implementation drift.

2. **Tripartite Cognitive Loop (`Actor -> Critic -> Arbitrator`)**:
   - **Actor**: Explores the codebase, executes tools, harvests log evidence, and drafts an initial hypothesis using fast model tiers (`gemini-3.7-flash`).
   - **Critic**: Performs an adversarial self-audit using reasoning model tiers (`gemini-3.1-pro-preview`), verifying claims against raw logs, schemas, and specifications while flagging ungrounded assumptions or hallucinations.
   - **Arbitrator**: Impartially evaluates Actor findings and Critic challenges, resolves discrepancies, produces a definitive verified verdict, and autonomously determines whether architectural or sequence diagrams are needed.

3. **Two-Tier Model Routing**:
   - **Flash Tier** (`gemini-3.7-flash`): Fast tool calling, ripgrep searches, schema inspections, log slicing, and timeline extraction.
   - **Pro Tier** (`gemini-3.1-pro-preview`): Complex root-cause reasoning, adversarial self-audit, and arbitrator synthesis.

4. **Dual Visualization Engine**:
   - **Graphviz (DOT)**: Generates structured, hierarchical architecture and network topology graphs compiled to SVG via the local `/usr/bin/dot` utility.
   - **Mermaid**: Generates sequence diagrams and protocol transaction flows (`sequenceDiagram`, `graph LR`).

---

## 2. Tooling Suite

Mantis exposes granular tool primitives across five functional tiers:

### Tier 1: Environment & Execution Control
- `ensure_test_setup`: Provisions an isolated local UDMI stack (Mosquitto broker, etcd, InfluxDB, PostgreSQL, UDMIS) in isolated tmux windows with non-privileged user-space ports.
- `terminate_test_setup`: Safely tears down isolated test sessions.
- `list_test_setups`: Lists active test infrastructure sessions.
- `list_test_windows`: Inspects named tmux windows (`main`, `dut`, `sequencer`, `butler`, `validator`).
- `get_test_logs`: Captures live console output from named windows.
- `run_sequencer_test`: Launches sequence tests against local or cloud endpoints (`//gbos/...`, `//gcp/...`).

### Tier 2: Real-time Inspection & Mutation
- `query_database`: Executes read-only SQL or Flux queries against isolated PostgreSQL or InfluxDB instances.
- `publish_mqtt_message`: Injects raw MQTT payloads for active triage.

### Tier 3: Specification & Site Model Grounding
- `inspect_udmi_schema`: Inspects official JSON schemas under `schema/` with recursive `$ref` resolution.
- `inspect_site_model`: Validates site models, device counts, and device metadata definitions.
- `patch_site_model`: Safely updates device `metadata.json` with automatic `.bak` backups and unified diff generation.

### Tier 4: Diagnostic Intelligence & Codebase Traversal
- `read_udmi_file`: Reads exact lines from source code, schemas, or specification documents.
- `search_codebase`: Fast ripgrep search across Java, Python, JSON, and Markdown files.
- `locate_udmi_doc`: Finds authoritative specs and guides in `docs/` matching a topic.
- `inspect_sequencer_test`: Dynamically parses Java test classes in `validator/.../sequencer/sequences/`, extracting features, stages, and assertions.
- `inspect_message_trace`: Inspects recorded MQTT message payloads (`events_pointset.json`, `state.json`, `config.json`).
- `detect_log_anomalies`: Identifies timing anomalies, clock drift, lagging state updates, and Jackson deserialization errors.
- `get_test_timeline`: Extracts chronological ISO timestamps, transaction IDs (`RC:...`), and cutoff transitions from logs.
- `compare_test_runs`: Performs behavioral differential sequence alignment between a target run and a reference baseline.
- `get_udmis_runtime_logs`: Retrieves authoritative UDMIS runtime execution logs across local files and cloud sinks, strictly enforcing evidence-tier boundaries (`LOCAL_FILE`, `CLOUD`, `NONE`, `UNAVAILABLE`, `INDETERMINATE`).
- `verify_golden_baseline`: Validates test outputs against golden baselines in `etc/` enforcing anti-cheating rules.

### Tier 5: Dual Visualization Engine
- `generate_topology_diagram`: Produces Graphviz DOT and Mermaid topology diagrams from site models.
- `generate_sequence_diagram`: Produces Graphviz DOT and Mermaid sequence diagrams from test execution logs.
- `render_dot_to_svg`: Compiles Graphviz DOT syntax to SVG using local `/usr/bin/dot`.

---

## 3. Navigational Skills (Playbooks)

Mantis uses procedural playbooks in `mantis/skills/` that teach the agent where and how to investigate the codebase:
1. `udmi-spec-navigation`: Locates authoritative specifications and message definitions.
2. `state-machine-investigation`: Analyzes config-state synchronization and transaction timestamps.
3. `sequencer-test-anatomy`: Parses Java sequencer test classes, `@Feature` annotations, and assertions.
4. `gateway-fieldbus-triage`: Investigates proxy devices, gateway bindings, and fieldbus error telemetry.
5. `log-anomaly-hunting`: Cross-references multi-service logs chronologically to isolate failure causes.
6. `database-inspection`: Validates telemetry persistence in PostgreSQL and InfluxDB.
7. `transport-and-target-routing`: Navigates target project specifications, broker URIs, and transport routing.
8. `udmi-architecture-and-components`: Maps component boundaries, evidence tiers, and UDMIS processor pipelines.

---

## 4. Usage

### Interactive Console
```bash
bin/mantis
```
Launches an interactive REPL session with conversational memory, streaming token generation, and command controls (`/status`, `/logs <window>`, `/clear`, `/export`, `/help`, `/exit`).

### Headless Execution
```bash
# Diagnostic query
bin/mantis "Why did pointset_publish fail for AHU-1?"

# Codebase exploration
bin/mantis "Find spec for writeback"

# Visual topology diagram
bin/mantis "Show topology diagram for sites/udmi_site_model"

# Schema inspection
bin/mantis "What are the required fields in pointset schema?"

# Test execution
bin/mantis "Run pointset_publish for AHU-1 in session dev_1"
```

### Support Bundle Ingestion
```bash
bin/mantis support_bundle.zip
```
Automatically extracts, ingests, and performs root-cause analysis on an archived diagnostic bundle.

### Model Context Protocol (MCP) Server
```bash
bin/mantis --mcp
```
Runs a standard stdio MCP server exposing all registered Mantis tools to external agent environments.

### Python API
```python
from mantis.agent import MantisAgent

agent = MantisAgent()

# Single-shot execution
response = agent.run("Why did pointset_publish fail for AHU-1?")

# Tripartite execution (Actor -> Critic -> Arbitrator)
result = agent.run_tripartite("Explain device state transitions")
print(result["final_answer"])
```

---

## 5. Testing

Run the comprehensive Mantis test suite:
```bash
bin/test_mantis
```
