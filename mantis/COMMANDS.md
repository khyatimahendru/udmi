# MANTIS Unified Command Interface Specification

This document defines the single, universally applicable execution model for Mantis.

---

## 1. The Single Universal Execution Paradigm

Previous versions of Mantis fragmented functionality across multiple competing subcommands (`chat`, `diagnose`, `eval`, `triage`, `collect`, `create-playbook`), positional argument formats (`sites/<site> <device> <test>`), and flag variations (`-q`, `-t`, `-d`, `-s`). This created unnecessary cognitive overhead and confusion.

Mantis implements **one universal way to execute any operation**:

```
Universal Execution Rule:
1. bin/mantis                     -> Launches the Interactive Diagnostic Session.
2. bin/mantis "<instruction>"     -> Executes any instruction or query headless and exits.
3. bin/mantis --mcp               -> Runs the stdio Model Context Protocol (MCP) server.
```

No subcommands. No conflicting positional formats. No duplicate flags.

### 1.1. Self-Bootstrapping Runtime Environment Guarantee
`bin/mantis` is completely self-bootstrapping. When invoked on a fresh repository clone or in an environment without a configured virtual environment, `bin/mantis` automatically:
1. Detects if `venv/bin/activate` or `venv/bin/python3` are missing.
2. Automatically triggers `bin/setup_base` to build the Python 3 virtual environment and install all dependencies.
3. Verifies `tmux` availability for isolated session management.
4. Activates `venv` and launches Mantis seamlessly.

---

## 2. Headless Universal Execution

Any action that Mantis can perform can be invoked by passing the instruction directly to `bin/mantis`. Mantis autonomously extracts target sites, devices, test cases, file paths, and execution intents, invokes the required tools, and outputs the result.

### 2.1. Examples of Universal CLI Invocations

```bash
# General Domain Question
bin/mantis "What are the required fields in pointset schema?"

# Test Execution
bin/mantis "Run pointset_publish for device AHU-1 on sites/udmi_site_model"

# Failure Triage & Root Cause Analysis
bin/mantis "Why did pointset_publish fail for AHU-1?"

# Environment Provisioning
bin/mantis "Start an isolated local environment for sites/udmi_site_model with DUT AHU-1"

# Environment Teardown
bin/mantis "Stop environment dev1"

# Multi-Run Stability Evaluation
bin/mantis "Evaluate stability of test runs in out/runs/"

# Support Bundle Triage
bin/mantis "Triage support bundle support_bundle.zip"

# Site Model Validation
bin/mantis "Validate site model sites/udmi_site_model"

# Configuration Patching
bin/mantis "Set sample_rate_sec to 10 for AHU-1 in sites/udmi_site_model"
```

If a file path or bundle archive is passed directly, Mantis automatically infers the operation:
```bash
bin/mantis support_bundle.zip     # Autonomously detected as bundle triage
```

---

## 3. Interactive Session Interface (`bin/mantis`)

When executed without arguments, `bin/mantis` starts the interactive session. 

Users interact with Mantis purely through **natural language instructions**. Users do not need to memorize synthetic command syntax or parameter flags.

```
$ bin/mantis
Mantis: Autonomous UDMI Agent & Diagnostic Console
[Context: sites/udmi_site_model | Active Session: None]

you > Start an isolated local stack with DUT AHU-1 and the validator enabled.
Mantis: Provisioning isolated environment 'udmi_dev_1'...
  * Allocated Port Block: MQTT=28430, etcd=28431, influx=28432, postgres=28433
  * Launched Tmux Session: 'udmi_dev_1' [main, dut, validator]
  * Control Plane Ready: Mosquitto online, certificates generated, UDMIS ready.
  * DUT: AHU-1 running in window 'dut'.
Environment 'dev_1' is ready at //mqtt/localhost:28430.

you > Run pointset_publish on AHU-1.
Mantis: Executing sequencer test 'pointset_publish' for AHU-1...
  * Target: //mqtt/localhost:28430
  * Result: FAIL (State synchronization timeout)

you > Why did it fail?
Mantis: Analyzing logs, timestamps, and schema definitions...

### Failure Diagnosis: `AHU-1` / `pointset_publish`

* **Root Cause**: Sequencer timed out (120s) because the device state update timestamp (`12:45:06Z`) lagged the sequencer cutoff threshold (`12:45:08Z`), triggering stale state rejection.
* **Evidence**:
  - Cutoff set at `12:45:08Z` (`sequence.log:84`)
  - Stale state update `12:45:06Z` ignored (`sequence.log:89`, `device_system.log:112`)
  - Config transaction `RC:9a6ddf.00000134` acknowledged by Pubber at `12:45:17Z`
* **Fix**:
  - `bin/mantis "Set sample_rate_sec to 10 for AHU-1"`
  - Or bypass state checks: `bin/mantis "Run pointset_publish on AHU-1 with nostate"`
```

---

## 4. Canonical Session Control Commands

To prevent user confusion, duplicate command aliases have been eliminated. There is **exactly one canonical command** for system-level session control operations:

| Command | Arguments | Purpose |
| :--- | :--- | :--- |
| `/status` | None | Displays current active context, environments, and port assignments. |
| `/logs` | `<window>` | Captures console buffer from a named tmux window (`main`, `dut`, `sequencer`, `butler`, `validator`). |
| `/clear` | None | Resets conversation history while preserving active sessions. |
| `/export` | `[filepath]` | Exports conversation history and diagnostic reports to a Markdown file. |
| `/help` | None | Displays help information and system status. |
| `/exit` | None | Terminates the interactive session. |

### 4.1. Rules for Session Commands
1. **Zero Synonyms / Aliases**: Synonyms such as `/ps`, `/env`, `/instances`, `/up`, `/setup`, `/ensure`, `/down`, `/stop`, `/terminate`, `/diff`, `/critique`, `/fact-check`, `/ctx` are removed.
2. **Domain Operations via Natural Language**: Operations like running tests, provisioning stacks, diffing logs, patching metadata, and querying schemas are executed directly by giving instructions to the agent.
3. **Deterministic System Controls**: The 6 slash commands (`/status`, `/logs`, `/clear`, `/export`, `/help`, `/exit`) exist solely for deterministic terminal controls that cannot be phrased ambiguously.

---

## 5. Model Context Protocol Integration

To run Mantis as an MCP server for IDEs and external agents, invoke the single `--mcp` flag:

```bash
bin/mantis --mcp
```

This starts the JSON-RPC 2.0 stdio server, exposing the full tool suite to external agents.
