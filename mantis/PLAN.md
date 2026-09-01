# MANTIS Implementation & Action Plan

This document outlines the step-by-step implementation roadmap for building the new Mantis platform in the root `mantis/` directory, establishing a clean, unified architecture with zero legacy technical debt. Do not look in the git repository for legacy implementation and build everything from scratch.

---

## 1. Architectural Principles & Coding Standards

Every module and interface in the new Mantis implementation strictly adheres to standard software engineering best practices:

### Core Design Philosophies
* **KISS (Keep It Simple, Stupid)**: Avoid over-engineered abstractions. Code is written directly for the UDMI ecosystem without unnecessary indirection or speculative multi-repo harnesses.
* **DRY (Don't Repeat Yourself)**: All process management, port derivation, and tool schemas are centralized in `mcp/`. Mantis agent and external MCP clients consume the exact same underlying tools.
* **YAGNI (You Aren't Gonna Need It)**: No dead code, no duplicate subcommands, and no redundant command aliases. Build only what is required by the specification.
* **Separation of Concerns (SoC)**: 
  * `mcp/`: Deterministic tool execution, database probing, and tmux process orchestration.
  * `mantis/`: Cognitive reasoning, prompt compilation, built-in adversarial critique, skill loading, and user interaction.

### SOLID Principles
* **Single Responsibility (SRP)**: Each module handles a single concern (e.g., `skills.py` handles skill discovery; `agent.py` handles ReAct reasoning).
* **Open/Closed (OCP)**: New protocols and hardware rules are added via markdown `SKILL.md` files without modifying core Python code.
* **Liskov Substitution (LSP)**: Model providers (Vertex AI vs Google AI Studio) conform to standard asynchronous streaming and content interfaces.
* **Interface Segregation (ISP)**: MCP tools expose minimal, orthogonal parameter contracts rather than monolithic black-box payloads.
* **Dependency Inversion (DIP)**: Agent logic interacts with tool abstractions rather than invoking raw shell commands or direct sockets.

### Maintenance & Quality
* **The Boy Scout Rule**: Zero copy-pasting of legacy anti-patterns (no hardcoded editorializing in tools, no broken control-flow branches, no duplicate `v1/v2` directories).
* **Readability over Cleverness**: Clean type hints (`typing`), explicit variable names, structured error handling, and standard docstrings throughout.
* **Testability**: Every component is isolated and unit-testable offline with mock fixtures and without external network dependencies.

### Clean Architecture & Unidirectional Dependency Rules
* **Layer 0 (Contracts & Schemas)**: `mantis/models.py` (Pydantic v2 data models for tool parameters, responses, diagnostic verification matrices, and session context). Has zero internal repository imports.
* **Layer 1 (Deterministic Tool & Substrate Layer)**: `mcp/` and `mantis/tools/*` (Pure deterministic functions; must NEVER import or depend on `agent.py`, `chat.py`, `cli.py`, or `context.py`).
* **Layer 2 (Cognitive Layer)**: `mantis/agent.py` (ReAct planning, function calling, tool orchestration).
* **Layer 3 (Context & State Layer)**: `mantis/context.py` & `mantis/chat.py` (Stateful multi-turn history, entity tracking, log compaction).
* **Layer 4 (Interfaces & Entrypoints)**: `mantis/cli.py` & `mcp/server.py`.

---

## 2. Target File & Package Structure

```
udmi/
├── mantis/                           # Unified Agent & Cognitive Core
│   ├── __init__.py
│   ├── models.py                     # Layer 0: Pydantic v2 data contracts & schemas
│   ├── context.py                    # Layer 3: Stateful multi-turn context & compaction
│   ├── cli.py                        # Universal CLI dispatcher (Interactive / Headless / --mcp)
│   ├── agent.py                      # ReAct cognitive planner with built-in adversarial critique
│   ├── chat.py                       # Interactive REPL console & canonical session controls
│   ├── config.py                     # Centralized model constants & provider configuration
│   ├── skills.py                     # Dynamic SKILL.md discovery and JIT context loader
│   ├── skills/                       # Built-in Markdown Skills Catalog
│   │   ├── log-analysis/SKILL.md
│   │   ├── component-guide/SKILL.md
│   │   └── investigation-strategy/SKILL.md
│   ├── tools/                        # Composable Domain Tool Adapters (Pure & Factual)
│   │   ├── __init__.py
│   │   ├── registry.py               # Canonical tool schemas & execution dispatcher
│   │   ├── artifacts.py              # Multi-path artifact discovery & log slicing
│   │   ├── diagnostics.py            # Deterministic diagnostic analysis & hypothesis evaluation
│   │   ├── differential.py           # Behavioral differential state machine alignment
│   │   ├── schemas.py                # JSON schema catalog & inspector
│   │   ├── site_models.py            # Site model config & device metadata inspector
│   │   ├── patcher.py                # Safe metadata & site config patcher (diffs + .bak)
│   │   ├── cloud_logs.py             # GCP Cloud Logging time-window queries
│   │   └── traces.py                 # MQTT recorded payload inspector
│   ├── tests/                        # 100% Offline Pytest Suite
│   │   ├── test_architecture.py      # AST-level architectural boundary enforcement
│   │   ├── test_models.py            # Pydantic v2 contract integrity tests
│   │   ├── test_context.py           # Multi-turn context & compaction tests
│   │   ├── test_diagnostics.py       # Adversarial critique & stability metrics tests
│   │   ├── test_mcp.py               # MCP JSON-RPC protocol & validation tests
│   │   ├── test_agent.py
│   │   ├── test_chat.py
│   │   ├── test_cli.py
│   │   ├── test_differential.py
│   │   ├── test_patcher.py
│   │   ├── test_schemas.py
│   │   ├── test_session_manager.py
│   │   ├── test_site_models.py
│   │   └── test_skills.py
│   ├── MANTIS.md                     # Primary System Specification
│   ├── COMMANDS.md                   # Universal CLI & Canonical REPL Specification
│   ├── DIAGNOSTICS.md                # Built-in Adversarial Critique Specification
│   ├── MCP.md                        # Model Context Protocol 4-Tier Specification
│   ├── SKILLS.md                     # Skill Extensibility Specification
│   └── PLAN.md                       # This implementation plan
│
├── mcp/                              # Unified Repository-Wide MCP Provider
│   ├── __init__.py
│   ├── server.py                     # Central JSON-RPC 2.0 stdio server & tool schemas
│   ├── session_manager.py            # Tmux session engine, port mapping, and log capture
│   └── mcp_config.json               # Canonical MCP configuration
│
└── bin/
    ├── mantis                        # Self-bootstrapping agent CLI entrypoint
    ├── test_infra_mcp                # Executable entrypoint for MCP server
    └── test_mantis                   # Comprehensive Mantis test suite runner
```

---

## 3. Regression Prevention Plan for `mcp/` and UDMI Subsystems

To prevent breaking existing `mcp/` tools used by other parts of the repository (such as `gummi/` or `bin/test_setup`):

1. **Additive & Backward-Compatible MCP Expansion**:
   * Existing methods in `mcp/session_manager.py` (`ensure_test_setup`, `terminate_test_setup`, `list_test_setups`, `get_test_logs`, `list_test_windows`) maintain their exact signatures and behavior.
   * New capabilities (`start_session_process`, `query_database`, `publish_mqtt_message`) are added as clean, independent methods.
2. **Deterministic Port Block Integrity**:
   * Port allocation formula ($BasePort \ge 20000$) remains untouched, ensuring multi-instance isolation without port collisions.
3. **Continuous Verification**:
   * Run `bin/test_infra_mcp list` and execute MCP unit tests after every modification to verify zero regression.

---

## 4. Step-by-Step Implementation Roadmap

### Phase 1: MCP Server & Session Engine Expansion (`mcp/`)
* **Task 1.1**: Extend `mcp/session_manager.py`:
  * Add `start_session_process(test_id, window, command, env)` to launch test processes (sequencer, Pubber, validator) into semantic tmux windows.
  * Add `query_database(test_id, database_type, query)` for live InfluxDB / PostgreSQL queries.
  * Add `publish_mqtt_message(test_id, topic, payload)` for active Mosquitto injection.
* **Task 1.2**: Update `mcp/server.py`:
  * Implement the complete 4-tier MCP tool catalog (`ensure_test_setup`, `start_session_process`, `get_test_logs`, `list_test_windows`, `list_test_setups`, `terminate_test_setup`, `query_database`, `publish_mqtt_message`, `inspect_udmi_schema`, `inspect_site_model`, `patch_site_model`, `get_test_timeline`, `compare_test_runs`, `diagnose_test_failure`).
  * Ensure standard JSON-RPC 2.0 error handling, Pydantic v2 contract validation, and asynchronous non-blocking stdio loop (`run_async` / `handle_request_async`) delegating blocking tools to background worker threads.

### Phase 2: Composable Domain Tools in `mantis/tools/`
* **Task 2.1**: Implement `mantis/tools/schemas.py`:
  * Fast JSON schema resolution and sub-property inspection under `schema/`.
* **Task 2.2**: Implement `mantis/tools/site_models.py`:
  * Clean parsing and querying of `cloud_iot_config.json` and device `metadata.json`.
* **Task 2.3**: Implement `mantis/tools/patcher.py`:
  * Safe atomic mutation with dry-run diff preview and automatic `.bak` snapshot backups.
* **Task 2.4**: Implement `mantis/tools/differential.py`:
  * Pure, uneditorialized behavioral differential sequence alignment between test runs.
* **Task 2.5**: Implement `mantis/tools/artifacts.py`:
  * Deterministic test run discovery, transaction ID (`RC:...`) mapping, and time-sliced log extraction.
* **Task 2.6**: Implement `mantis/tools/cloud_logs.py` & `traces.py`:
  * GCP Cloud Logging time-window queries and recorded MQTT trace inspection.

### Phase 3: Cognitive Agent Core & Built-In Adversarial Critique
* **Task 3.1**: Implement `mantis/config.py`:
  * Centralized constants for model routing (`Flash` vs `Pro`), timeout limits, and provider auto-detection (Vertex AI ADC vs AI Studio API Key vs Offline Deterministic Mode).
* **Task 3.2**: Implement `mantis/skills.py`:
  * Dynamic discovery and just-in-time progressive context loading of `SKILL.md` files from `mantis/skills/` and `sites/<site>/skills/`.
  * Copy built-in skills (`log-analysis`, `component-guide`, `investigation-strategy`) into `mantis/skills/`.
* **Task 3.3**: Implement `mantis/agent.py`:
  * Clean ReAct cognitive loop with streaming token output.
  * Mandatory 3-phase cognitive cycle (*Hypothesis -> Claim Extraction & Verification Matrix -> Verified Synthesis*).
  * Automated competing hypothesis invalidation (Jackson parser vs stale state cutoff vs network loss).
  * Correct thought-enforcement verification during streaming execution.

### Phase 4: Universal CLI & Interactive REPL Console
* **Task 4.1**: Implement `mantis/chat.py`:
  * Interactive terminal REPL with live streaming thoughts, tool-call visualizers, and the 6 canonical commands (`/status`, `/logs`, `/clear`, `/export`, `/help`, `/exit`).
  * Route all domain operations directly through natural language instructions.
* **Task 4.2**: Implement `mantis/cli.py`:
  * Single universal dispatcher supporting:
    1. `bin/mantis` $\rightarrow$ Interactive REPL session.
    2. `bin/mantis "<instruction>"` $\rightarrow$ Headless single-shot execution.
    3. `bin/mantis --mcp` $\rightarrow$ Delegate directly to `mcp.server.main()`.
* **Task 4.3**: Update `bin/mantis`:
  * Finalize self-bootstrapping checks (`venv` verification, automatic `bin/setup_base` trigger, and `tmux` validation).

### Phase 5: Testing Suite & Two-Stage Verification
* **Task 5.1**: Build `mantis/tests/`:
  * Unit tests for agent reasoning, built-in critic verification matrix, skills loading, schema inspectors, differential timeline alignment, and CLI argument routing (100% offline with mocks).
* **Task 5.2**: Update `bin/test_mantis`:
  * Configure `bin/test_mantis` to execute `mantis/tests/` using pytest.
* **Task 5.3**: Two-Stage Verification:
  * Stage 1: `bin/test_mantis` and `bin/run_tests all_tests`.
  * Stage 2: Provision local stack, trigger sequencer tests, and verify end-to-end telemetry pipeline integrity.

---

## 5. Execution Checkpoints & Sign-Off

At the completion of each phase, the test suite must pass with 100% success before proceeding to the next phase. No unstaged or broken code will be committed.
